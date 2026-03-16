import logging
import time
from pathlib import Path
from typing import Union

import faiss  # type: ignore
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from kneed import KneeLocator  # type: ignore
from mind.pipeline.utils import get_doc_top_tpcs
from mind.utils.utils import init_logger, get_optimization_settings
from scipy import sparse
from scipy.ndimage import uniform_filter1d
from sentence_transformers import SentenceTransformer, util  # type: ignore
from tqdm import tqdm  # type: ignore


class IndexRetriever:
    def __init__(
        self, 
        model: SentenceTransformer, 
        top_k: int = 10,
        batch_size: int = 32,
        min_clusters: int = 8,
        n_clusters_ann: int = 100,
        nprobe: int = 10,
        nprobe_fixed : bool = False,
        do_norm: bool = False,
        do_weighting: bool = True,
        logger: logging.Logger = None,
        config_path: Path = Path("config/config.yaml")
    ):
        self._logger = logger if logger else init_logger(config_path, __name__)
        
        # OPT-002: Load optimization settings for batched embeddings
        self._opt_settings = get_optimization_settings(str(config_path), self._logger)
        self._batched_embeddings = self._opt_settings.get("batched_embeddings", False)
        if self._batched_embeddings:
            self._logger.info("OPT-002: Batched embeddings enabled")
    
        self.model = model
        self.batch_size = batch_size
        self.top_k = top_k
        self.min_clusters = min_clusters
        self.n_clusters_ann = n_clusters_ann
        self.nprobe = nprobe
        self.nprobe_fixed = nprobe_fixed
        self.do_norm = do_norm
        self.do_weighting = do_weighting
        
        self.model_name = getattr(model, "name_or_path", "")
        self.is_bge = "bge-m3" in self.model_name.lower() or "e5-large" in self.model_name.lower()
        
        self.faiss_index = None
        self.doc_ids = None
        self.topic_indices = None  # only for TB-ENN and TB-ANN
        self.index_method = None
        self.save_path = None
        self.thrs = None 
        
    def _prefix(self, texts, is_query: bool):
        if not self.is_bge:
            return texts
        self._logger.debug("Using BGE/E5 model, adding prefixes to texts.")
        pfx = "query: " if is_query else "passage: "
        return [t if t.startswith(pfx) else (pfx + t) for t in texts]

    # =========================================================================
    # OPT-002: Batched Query Embeddings
    # =========================================================================
    
    def encode_queries(self, queries, batch_size: int = None) -> np.ndarray:
        """
        Batch encode multiple queries for efficient GPU utilization.
        
        Parameters
        ----------
        queries : str or List[str]
            Single query or list of queries to encode.
        batch_size : int, optional
            Batch size for encoding. Defaults to self.batch_size.
            
        Returns
        -------
        np.ndarray
            Embeddings array of shape (n_queries, embedding_dim).
        """
        batch_size = batch_size or self.batch_size
        
        if isinstance(queries, str):
            queries = [queries]
        
        queries = self._prefix(queries, is_query=True)
        
        if self.do_norm:
            embeddings = self.model.encode(
                queries,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
        else:
            embeddings = self.model.encode(
                queries,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True
            )
        
        return embeddings.astype(np.float32)
    
    def _retrieve_enn_with_embedding(self, query_embedding: np.ndarray, top_k: int = None) -> list:
        """
        ENN retrieval with pre-computed embedding.
        
        Parameters
        ----------
        query_embedding : np.ndarray
            Pre-computed query embedding of shape (embedding_dim,) or (1, embedding_dim).
        top_k : int, optional
            Number of results to return. Defaults to self.top_k.
            
        Returns
        -------
        list
            List of dicts with doc_id and score.
        """
        top_k = top_k or self.top_k
        
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        
        distances, indices = self.faiss_index.search(
            query_embedding.astype(np.float32), 
            top_k
        )
        
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx >= 0:
                results.append({
                    "doc_id": self.doc_ids[idx],
                    "score": float(dist)
                })
        return results
    
    def _retrieve_topic_with_embedding(
        self, 
        query_embedding: np.ndarray, 
        theta_query: list, 
        top_k: int = None,
        thrs: list = None,
        do_weighting: bool = None
    ) -> list:
        """
        Topic-based retrieval with pre-computed embedding.
        
        Parameters
        ----------
        query_embedding : np.ndarray
            Pre-computed query embedding.
        theta_query : list
            Topic distribution for the query.
        top_k : int, optional
            Number of results to return.
        thrs : list, optional
            Topic thresholds.
        do_weighting : bool, optional
            Whether to weight scores by topic weights.
            
        Returns
        -------
        list
            Sorted list of results with doc_id, topic, and score.
        """
        top_k = top_k or self.top_k
        do_weighting = do_weighting if do_weighting is not None else self.do_weighting
        
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        
        results = []
        for topic, weight in theta_query:
            thr = thrs[topic] if thrs is not None else 0
            if weight > thr:
                topic_data = self.topic_indices.get(topic)
                if topic_data and topic_data["index"] is not None:
                    index = topic_data["index"]
                    doc_ids = topic_data["doc_ids"]
                    distances, indices = index.search(query_embedding.astype(np.float32), top_k)
                    for dist, idx in zip(distances[0], indices[0]):
                        if idx != -1:
                            score = dist * weight if do_weighting else dist
                            results.append({"topic": topic, "doc_id": doc_ids[idx], "score": score})
        
        # Remove duplicates, keeping highest score
        unique_results = {}
        for result in results:
            doc_id = result["doc_id"]
            if doc_id not in unique_results or result["score"] > unique_results[doc_id]["score"]:
                unique_results[doc_id] = result
        
        return sorted(unique_results.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    def _safe_nprobe(self, nlist: int) -> int:
        # Start around 10% of nlist. Clamp by [1, self.nprobe] and by nlist itself.
        if self.nprobe_fixed:
            return self.nprobe
        else:
            target = max(1, int(round(0.10 * max(1, nlist))))
            return max(1, min(target, int(self.nprobe), int(max(1, nlist))))

    def dynamic_thresholds(
        self,
        mat_, 
        poly_degree=3, 
        smoothing_window=5
    ):
        '''
        Computes the threshold on the document-topic distribution dynamically.
        '''
        thrs = []
        for k in range(len(mat_.T)):
            allvalues = np.sort(mat_[:, k].flatten())
            step = int(np.round(len(allvalues) / 1000))
            step = max(1, step)  # Ensure step is at least 1
            
            x_values = allvalues[::step]
            y_values = (100 / len(allvalues)) * np.arange(0, len(allvalues))[::step]
            
            # Check if we have enough points for smoothing
            if len(y_values) < smoothing_window:
                # Fallback: use 75th percentile
                threshold = np.percentile(mat_[:, k], 75)
                thrs.append(threshold)
                continue
            
            y_values_smooth = uniform_filter1d(y_values, size=smoothing_window)
            
            try:
                kneedle = KneeLocator(x_values, y_values_smooth, curve='concave', direction='increasing', interp_method='polynomial', polynomial_degree=poly_degree)
                
                if kneedle.elbow is not None:
                    thrs.append(kneedle.elbow)
                else:
                    # Fallback: use 75th percentile if no elbow found
                    threshold = np.percentile(mat_[:, k], 75)
                    thrs.append(threshold)
            except Exception:
                # Fallback: use 75th percentile if knee detection fails
                threshold = np.percentile(mat_[:, k], 75)
                thrs.append(threshold)
                
        return thrs
    
    def load_indices(self, method: str, source_path: str, thetas_path: str, save_path_parent: str):
        self.index_method = method
        self.save_path = (
            Path(save_path_parent)
            / Path(source_path).stem
            / Path(thetas_path).parent.parent.stem
            / method
        )
        
        # OPT-011: Check if memory-mapped loading is enabled
        use_mmap = self._opt_settings.get("faiss_mmap", False)
        io_flags = faiss.IO_FLAG_MMAP if use_mmap else 0
        if use_mmap:
            self._logger.info("OPT-011: Using memory-mapped FAISS indices")

        if method in ["ENN", "ANN"]:
            index_path = self.save_path / "faiss_index.index"
            doc_ids_path = self.save_path / "doc_ids.npy"
            if index_path.exists() and doc_ids_path.exists():
                self._logger.info(f"Loading FAISS index and doc_ids for method {method}...")
                self.faiss_index = faiss.read_index(str(index_path), io_flags)
                if method == "ANN":
                    # cap nprobe by nlist if available
                    self.faiss_index.nprobe = self._safe_nprobe(getattr(self.faiss_index, "nlist", 0))
                self.doc_ids = np.load(doc_ids_path, allow_pickle=True)
            else:
                raise FileNotFoundError(f"Index or doc_ids not found for method {method}.")
        
        elif method in ["TB-ENN", "TB-ANN"]:
            self.topic_indices = {}
            for index_file in self.save_path.glob("faiss_index_topic_*.index"):
                topic = int(index_file.stem.split("_")[-1])
                doc_ids_path = self.save_path / f"doc_ids_topic_{topic}.npy"
                if doc_ids_path.exists():
                    index = faiss.read_index(str(index_file), io_flags)
                    if method == "TB-ANN":
                        index.nprobe = self._safe_nprobe(getattr(index, "nlist", 0))
                    doc_ids = np.load(doc_ids_path, allow_pickle=True)
                    self.topic_indices[topic] = {"index": index, "doc_ids": doc_ids}
            if not self.topic_indices:
                raise FileNotFoundError(f"No topic-based indices found in {self.save_path}.")

            if self.thrs is None:  # <-- only compute if we don't already have thresholds
                thetas = sparse.load_npz(Path(thetas_path))
                thetas = thetas.toarray() if sparse.issparse(thetas) else thetas
                self.thrs = self.dynamic_thresholds(thetas)
    
    def index(
        self,
        source_path:str,
        save_path_parent:str,
        thetas_path:str=None,
        col_to_index:str="chunk_text",
        col_id:str="chunk_id",
        row_top_k = "top_k",
        lang:str=None, # if lang is given, it will be used to filter the dataframe
        thr_assignment: Union[float, str] = "var",
        method:str = "TB-ENN",
        load_thetas: bool = False,
    ):  
        save_path = (
            Path(save_path_parent)
            / Path(source_path).stem
            / Path(thetas_path).parent.parent.stem
            / method
        )
        save_path.mkdir(parents=True, exist_ok=True)
        
        df = pd.read_parquet(source_path)
        if lang:
            if "lang" in df.columns:
                df = df[df["lang"] == lang].copy()
            else:
                df = df[df[col_id].str.contains(lang)].copy()
                
        # calculate contextualized embeddings for the corpus
        texts = self._prefix(df[col_to_index].tolist(), is_query=False)
        #corpus_embeddings = self.model.encode(df[col_to_index].tolist(), show_progress_bar=True, convert_to_numpy=True, batch_size=self.batch_size)
        corpus_embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True, batch_size=self.batch_size).astype("float32")
        # normalize 
        if self.do_norm:
            corpus_embeddings = corpus_embeddings / np.linalg.norm(corpus_embeddings, axis=1, keepdims=True)
        embedding_size = corpus_embeddings.shape[1]

        if method in ["ENN", "ANN"]:            
            self._logger.info(f"Creating {method} indices")
            quantizer = faiss.IndexFlatIP(embedding_size)
            
            N = len(corpus_embeddings)
            n_clusters_ann =  max(int(4 * np.sqrt(N)), self.min_clusters) #self.n_clusters_ann
            
            index = (
                faiss.IndexIVFFlat(quantizer, embedding_size, n_clusters_ann, faiss.METRIC_INNER_PRODUCT)
                if method == 'ANN' else quantizer
            )
            
            if method == 'ANN':
                index.train(corpus_embeddings)
                index.nprobe = self._safe_nprobe(getattr(index, "nlist", 0))
        
            index.add(corpus_embeddings)
            
            faiss.write_index(index, (save_path / "faiss_index.index").as_posix())
            # save doc_ids
            np.save((save_path / "doc_ids.npy").as_posix(), df[col_id].values)
            

        elif method in ["TB-ENN", "TB-ANN"]:
            
            if load_thetas:
                thetas = sparse.load_npz(Path(thetas_path))
            
                # check if thetas is a sparse matrix, if so convert to dense
                if sparse.issparse(thetas):
                    thetas = thetas.toarray()
                df["thetas"] = list(thetas)
                df[row_top_k] = df["thetas"].apply(lambda x: get_doc_top_tpcs(x, topn=self.top_k))
            
            else:
                if row_top_k not in df.columns:
                    raise ValueError(f"Column {row_top_k} not found in dataframe. If thetas are not precomputed, please set load_thetas=True to compute them from thetas_path.")         
                            
            # determine threshold for topic assignment
            if thr_assignment == "var":
                thetas = np.array(list(df["thetas"]))
                thrs = self.dynamic_thresholds(thetas)
            else:
                thrs = thr_assignment * np.ones(thetas.shape[1])
            self.thrs = thrs  # persist thresholds for retrieval
            
            topic_indices = {}
            for topic in tqdm(range(thetas.shape[1]), desc="Creating index"):   
                this_tpc_thr = thrs[topic]
                index_path = save_path / f"faiss_index_topic_{topic}.index"
                doc_ids_path = save_path / f"doc_ids_topic_{topic}.npy"

                if index_path.exists() and doc_ids_path.exists():
                    continue

                self._logger.info(f"-- Creating index for topic {topic}...")
                topic_embeddings = []
                doc_ids = []

                for i, top_k in enumerate(df[row_top_k]):
                    for t, weight in top_k:
                        if t == topic and weight > this_tpc_thr:
                            topic_embeddings.append(corpus_embeddings[i])
                            doc_ids.append(df.iloc[i][col_id])
                if topic_embeddings:
                    topic_embeddings = np.array(topic_embeddings).astype("float32")
                    
                    N = len(topic_embeddings)
                    n_clusters = max(int(4 * np.sqrt(N)), self.min_clusters)
                    
                    self._logger.info(f"-- TOPIC {topic}: {N} documents, {n_clusters} clusters")
                    
                    # Train IVF index
                    embedding_size = topic_embeddings.shape[1]
                    quantizer = faiss.IndexFlatIP(embedding_size)

                    index = (
                        faiss.IndexIVFFlat(quantizer, embedding_size, n_clusters, faiss.METRIC_INNER_PRODUCT)
                        if method == 'TB-ANN' else quantizer
                    )
                    
                    if method == 'TB-ANN':
                        index.train(topic_embeddings)
                        index.nprobe = self._safe_nprobe(getattr(index, "nlist", 0))
                    # Add the topic embeddings to the index
                    index.add(topic_embeddings)
                    
                    # Save the index and document IDs
                    faiss.write_index(index, str(index_path))
                    np.save(doc_ids_path, np.array(doc_ids))
                    topic_indices[topic] = {"index": index, "doc_ids": doc_ids}
                else:
                    self._logger.info(f"-- No documents found for topic {topic} with threshold {this_tpc_thr}.")
                    topic_indices[topic] = {"index": None, "doc_ids": None}
                    
        self._logger.info(f"Indices created and saved in {save_path}")
        
        self.load_indices(
            method=method,
            source_path=source_path,
            thetas_path=thetas_path,
            save_path_parent=save_path_parent
        )
            
        return
    
    def build_or_load_index(
        self,
        source_path: str,
        thetas_path: str,
        save_path_parent: str,
        method: str = "TB-ENN",
        lang: str = "EN",
        col_to_index:str="chunk_text",
        col_id:str="chunk_id",
        **index_kwargs
    ):
        save_path = (
            Path(save_path_parent)
            / Path(source_path).stem
            / Path(thetas_path).parent.parent.stem
            / method
        )

        if method in ["ENN", "ANN"]:
            index_path = save_path / "faiss_index.index"
            doc_ids_path = save_path / "doc_ids.npy"
            if index_path.exists() and doc_ids_path.exists():
                self._logger.info(f"Existing index found for {method}. Loading...")
                return self.load_indices(method, source_path, thetas_path, save_path_parent)

        elif method in ["TB-ENN", "TB-ANN"]:
            any_index = list(save_path.glob("faiss_index_topic_*.index"))
            if any_index:
                self._logger.info(f"Existing topic-based indices found for {method}. Loading...")
                return self.load_indices(method, source_path, thetas_path, save_path_parent)

        self._logger.info(f"No existing index found for {method}. Building index...")
        self.index(
            source_path=source_path,
            thetas_path=thetas_path,
            col_to_index=col_to_index,
            col_id=col_id,
            save_path_parent=save_path_parent,
            method=method,
            lang=lang,
            **index_kwargs
        )

    
    def retrieve_enn_ann(self, query: str, top_k: int = 10):
        if self.faiss_index is None or self.doc_ids is None:
            raise ValueError("FAISS index or doc_ids not loaded. Make sure to call load_indices first.")

        # OPT-002: Use batched encoding if enabled
        if self._batched_embeddings:
            query_embedding = self.encode_queries(query)[0]  # Returns (1, dim), take first
            return self._retrieve_enn_with_embedding(query_embedding, top_k)
        
        # Original single-query encoding
        q = self._prefix([query], is_query=True)
        if self.do_norm:
            query_embedding = self.model.encode(q, normalize_embeddings=True)[0]  # shape: (dim,)
        else:
            query_embedding = self.model.encode(q, convert_to_numpy=True)[0]  # shape: (dim,)
        distances, indices = self.faiss_index.search(np.expand_dims(query_embedding, axis=0), top_k)

        return [
            {"doc_id": self.doc_ids[idx], "score": distances[0][i]}
            for i, idx in enumerate(indices[0]) if idx != -1
        ]
        
    def retrieve_topic_faiss(self, query, theta_query, top_k=10, thrs=None, do_weighting=None):
        
        do_weighting = do_weighting if do_weighting is not None else self.do_weighting
        
        if self.topic_indices is None:
            raise ValueError("Topic-based indices not loaded.")

        # OPT-002: Use batched encoding if enabled
        if self._batched_embeddings:
            query_embedding = self.encode_queries(query)[0]  # Returns (1, dim), take first
            return self._retrieve_topic_with_embedding(
                query_embedding, theta_query, top_k, thrs, do_weighting
            )
        
        # Original single-query encoding
        if self.do_norm:
            query_embedding = self.model.encode([query], normalize_embeddings=True)[0]
        else:
            query_embedding = self.model.encode([query], convert_to_numpy=True)[0]

        results = []
        for topic, weight in theta_query:
            thr = thrs[topic] if thrs is not None else 0
            if weight > thr:
                topic_data = self.topic_indices.get(topic)
                if topic_data and topic_data["index"] is not None:
                    index = topic_data["index"]
                    doc_ids = topic_data["doc_ids"]
                    distances, indices = index.search(np.expand_dims(query_embedding, axis=0), top_k)
                    for dist, idx in zip(distances[0], indices[0]):
                        if idx != -1:
                            score = dist * weight if do_weighting else dist
                            results.append({"topic": topic, "doc_id": doc_ids[idx], "score": score})

        # Remove duplicates, keeping the highest score
        unique_results = {}
        for result in results:
            doc_id = result["doc_id"]
            if doc_id not in unique_results or result["score"] > unique_results[doc_id]["score"]:
                unique_results[doc_id] = result

        return sorted(unique_results.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    
    def retrieve(
        self, 
        query: str, 
        theta_query: list = None, 
        top_k: int = None, 
        thrs_opt=None, #if var use self.thr
        do_weighting: bool = False
    ):  
        top_k = top_k or self.top_k
        time_start = time.time()
        if self.index_method in ["ENN", "ANN"]:
            results =  self.retrieve_enn_ann(query, top_k)
        elif self.index_method in ["TB-ENN", "TB-ANN"]:
            if theta_query is None:
                raise ValueError("theta_query must be provided for topic-based retrieval.")
            results =  self.retrieve_topic_faiss(
                query=query,
                theta_query=theta_query,
                top_k=top_k,
                thrs=self.thrs if thrs_opt == "var" else thrs_opt,
                do_weighting=do_weighting
            )
        else:
            raise ValueError(f"Unknown index method: {self.index_method}")
        
        time_end = time.time()

        return results, time_end - time_start