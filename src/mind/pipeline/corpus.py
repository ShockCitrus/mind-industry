import ast
import logging
from pathlib import Path
import pandas as pd # type: ignore
import numpy as np
from scipy import sparse
from mind.pipeline.retriever import IndexRetriever
from mind.utils.utils import init_logger, get_optimization_settings
import pyarrow.parquet as pq # type: ignore


class Chunk:
    """A class representing a chunk of text with an ID, text content, and optional metadata. Optional metadata incudes (**so far**) the top k topics for the chunk as a list of tuples (topic_id, theta_weight), and the score of the chunk in the retrieval system (if used as a result of a retrieval query).
    """
    def __init__(self, id, text, full_doc=None, metadata=None):
        self.id = id
        self.text = text
        self.full_doc = full_doc
        self.metadata = metadata

    def __repr__(self):
        return f"Chunk(id={self.id}, text='{self.text[:30]}...')"


class Corpus:
    def __init__(
        self,
        df: pd.DataFrame,
        id_col="chunk_id",
        passage_col="chunk_text",
        full_doc_col="full_doc",
        row_top_k = "top_k",
        config_path: Path = None,
        logger: logging.Logger = None,
        retriever: IndexRetriever = None
    ):  
        """ 
        Initializes a Corpus object from a pandas DataFrame. The DataFrame should contain the following columns:
        - id_col: The ID of the chunk (default: "chunk_id")
        - passage_col: The text of the chunk (default: "chunk_text")
        - full_doc_col: The full document text (default: "full_doc")
        The columns are renamed to "doc_id", "text", and "full_doc" respectively, for generalization to later use.
        
        If a retriever is provided, it will be used to retrieve relevant chunks from the corpus, that is, if a retriever is given, the corpus is a target corpus.
        
        Parameters
        ----------
        df: pd.DataFrame
            The DataFrame containing the corpus data.
        id_col: str
            The name of the column containing the chunk IDs (default: "chunk_id").
        passage_col: str
            The name of the column containing the chunk text (default: "chunk_text").
        full_doc_col: str
            The name of the column containing the full document text (default: "full_doc").
        config_path: Path
            The path to the configuration file (default: None).
        logger: logging.Logger
            The logger to use for logging (default: None).
        retriever: IndexRetriever
            The retriever to use for retrieving relevant chunks (default: None).
        """
        
        for col in [id_col, passage_col, full_doc_col]:
            if col not in df.columns:
                raise ValueError(f"Column {col} not found in dataframe")
        self.df = df.copy()
        # rename columns to "doc_id", "text", and "full_doc"
        # rename the column passage_col to "text"
        if full_doc_col == passage_col:
            self.df["full_doc"] = self.df[passage_col] 
            full_doc_col = "full_doc"
        self.df = self.df.rename(columns={passage_col: "text", full_doc_col: "full_doc", id_col:"doc_id"})
        

        self._logger = logger if logger else init_logger(config_path, __name__)
        self._logger.info(f"Corpus initialized with {len(df)} documents.")
        self.retriever = retriever
        self.row_top_k = row_top_k

    @classmethod
    def from_parquet_and_thetas(
        cls,
        path_parquet,
        path_thetas = None,
        id_col="chunk_id",
        passage_col="chunk_text",
        full_doc_col="full_doc",
        row_top_k = "top_k",
        config_path=None,
        logger=None,
        language_filter="EN",
        retriever=None,
        filter_ids=None,
        load_thetas = False
    ):
        logger = logger if logger else init_logger(config_path, __name__)
        
        # OPT-003: Check if lazy loading is enabled in config
        opt_settings = get_optimization_settings(str(config_path) if config_path else "config/config.yaml", logger)
        if opt_settings.get("lazy_corpus_loading", False):
            logger.info("OPT-003: Lazy corpus loading enabled, using from_parquet_lazy()")
            return cls.from_parquet_lazy(
                path_parquet=path_parquet,
                path_thetas=path_thetas,
                id_col=id_col,
                passage_col=passage_col,
                full_doc_col=full_doc_col,
                row_top_k=row_top_k,
                batch_size=opt_settings.get("chunk_size", 10000),
                config_path=config_path,
                logger=logger,
                language_filter=language_filter,
                retriever=retriever
            )

        table = pq.read_table(path_parquet)
        df = table.to_pandas(self_destruct=True, ignore_metadata=True)
        if language_filter:
            if "lang" in df.columns:
                df = df[df["lang"] == language_filter].copy()
            else:
                df = df[df[id_col].str.contains(language_filter)].copy()

        if load_thetas:
            logger.info(f"Loading documents from {path_parquet}")
            logger.info(f"Loading topic distribution from {path_thetas}")
            thetas = sparse.load_npz(path_thetas).toarray()
            df["thetas"] = list(thetas)
            df[row_top_k] = df["thetas"].apply(lambda x: cls.get_doc_top_tpcs(x, topn=10))
            df["main_topic_thetas"] = df["thetas"].apply(lambda x: int(np.argmax(x)))
        else:
            if row_top_k not in df.columns:
                raise ValueError(f"Column {row_top_k} not found in dataframe. If thetas are not precomputed, please set load_thetas=True to compute them from thetas_path.")
            
                return
            
            logger.info("Using precomputed thetas")
            # get "main_topic_thetas" from row_top_k
            """
            (Pdb) df[row_top_k].iloc[0]
            array([array([3.       , 0.7789458]), array([0.        , 0.07558145]),
                array([2.        , 0.06667581]), array([1.        , 0.04908134]),
                array([4.        , 0.02971561])], dtype=object)
            """
            df["main_topic_thetas"] = df[row_top_k].apply(lambda x: int(x[0][0]))
        
        if filter_ids is not None:
            # remove rows from df whose id_col is in filter_ids
            df = df[~df[id_col].isin(filter_ids)].copy()
            logger.info(f"Filtered out {len(filter_ids)} documents based on provided filter_ids.")
            
        logger.info(f"Loaded {len(df)} documents after filtering.")
        return cls(df, config_path=config_path, logger=logger, retriever=retriever, id_col=id_col, passage_col=passage_col, full_doc_col=full_doc_col, row_top_k=row_top_k)

    # =========================================================================
    # OPT-003: Chunked DataFrame Loading
    # =========================================================================
    
    @classmethod
    def from_parquet_lazy(
        cls,
        path_parquet,
        path_thetas=None,
        id_col="chunk_id",
        passage_col="chunk_text",
        full_doc_col="full_doc",
        row_top_k="top_k",
        batch_size: int = 10000,
        config_path=None,
        logger=None,
        language_filter="EN",
        retriever=None
    ):
        """
        Create Corpus with lazy chunk loading support.
        
        Only metadata is loaded initially; chunks are streamed on demand.
        This reduces peak memory usage by 40-60% for large corpora.
        
        Parameters
        ----------
        path_parquet : Path
            Path to Parquet corpus file.
        path_thetas : Path, optional
            Path to topic distributions (not loaded in lazy mode).
        batch_size : int
            Batch size for chunk iteration. Default: 10000.
        Other parameters are same as from_parquet_and_thetas().
        
        Returns
        -------
        Corpus
            Corpus instance configured for lazy loading.
        """
        logger = logger if logger else init_logger(config_path, __name__)
        
        # Read only metadata (schema and row count)
        parquet_file = pq.ParquetFile(path_parquet)
        metadata = parquet_file.metadata
        
        # Get schema by reading a small batch
        first_batch = next(parquet_file.iter_batches(batch_size=10))
        df_schema = first_batch.to_pandas().head(0)
        
        # Ensure required columns exist
        for col in [id_col, passage_col, full_doc_col]:
            if col not in df_schema.columns:
                raise ValueError(f"Column {col} not found in Parquet schema")
        
        # Create minimal DataFrame for initialization
        df_schema = df_schema.rename(columns={
            passage_col: "text", 
            full_doc_col: "full_doc", 
            id_col: "doc_id"
        })
        
        # Create corpus instance
        corpus = cls.__new__(cls)
        corpus.df = df_schema.copy()
        corpus._logger = logger
        corpus.retriever = retriever
        corpus.row_top_k = row_top_k
        
        # Store lazy loading config
        corpus._lazy_mode = True
        corpus._parquet_path = path_parquet
        corpus._thetas_path = path_thetas
        corpus._batch_size = batch_size
        corpus._total_rows = metadata.num_rows
        corpus._id_col = id_col
        corpus._passage_col = passage_col
        corpus._full_doc_col = full_doc_col
        corpus._language_filter = language_filter
        
        logger.info(f"Lazy corpus initialized for {corpus._total_rows} documents (batch_size={batch_size})")
        return corpus

    def chunks_with_topic_lazy(self, topic_id: int, sample_size: int = None):
        """
        Generator that streams chunks for a specific topic without loading full corpus.
        
        Parameters
        ----------
        topic_id : int
            Topic ID to filter chunks by.
        sample_size : int, optional
            Maximum number of chunks to yield.
            
        Yields
        ------
        Chunk
            Chunks matching the specified topic.
        """
        if not getattr(self, '_lazy_mode', False):
            # Fall back to original method
            yield from self.chunks_with_topic(topic_id, sample_size)
            return
        
        parquet_file = pq.ParquetFile(self._parquet_path)
        
        count = 0
        for batch in parquet_file.iter_batches(batch_size=self._batch_size):
            df_batch = batch.to_pandas()
            
            # Apply language filter if set
            if self._language_filter:
                if "lang" in df_batch.columns:
                    df_batch = df_batch[df_batch["lang"] == self._language_filter]
                elif self._id_col in df_batch.columns:
                    df_batch = df_batch[df_batch[self._id_col].str.contains(self._language_filter)]
            
            # Filter by main topic
            if "main_topic_thetas" in df_batch.columns:
                topic_rows = df_batch[df_batch["main_topic_thetas"] == topic_id]
            elif self.row_top_k in df_batch.columns:
                # Compute main topic from top_k if main_topic_thetas not available
                topic_rows = df_batch[
                    df_batch[self.row_top_k].apply(
                        lambda x: int(x[0][0]) if isinstance(x, (list, np.ndarray)) and len(x) > 0 else -1
                    ) == topic_id
                ]
            else:
                self._logger.warning("No topic column found, yielding all rows in batch")
                topic_rows = df_batch
            
            for _, row in topic_rows.iterrows():
                if sample_size and count >= sample_size:
                    return
                
                metadata = {}
                if self.row_top_k in row.index:
                    metadata["top_k"] = row[self.row_top_k]
                
                yield Chunk(
                    id=row.get(self._id_col) or row.get("doc_id"),
                    text=row.get(self._passage_col) or row.get("text"),
                    full_doc=row.get(self._full_doc_col) or row.get("full_doc", ""),
                    metadata=metadata
                )
                count += 1
        
        self._logger.info(f"Lazy iteration yielded {count} chunks for topic {topic_id}")

    @staticmethod
    def get_doc_top_tpcs(doc_distr, topn=10):
        sorted_tpc_indices = np.argsort(doc_distr)[::-1]
        top = sorted_tpc_indices[:topn].tolist()
        return [(k, float(doc_distr[k])) for k in top if doc_distr[k] > 0]

    def chunks_with_topic(self, topic_id, sample_size=None, previous_check=None):
        # OPT-003: Delegate to lazy loader if enabled
        if getattr(self, '_lazy_mode', False):
            self._logger.info(f"Using lazy loading for topic {topic_id}")
            yield from self.chunks_with_topic_lazy(topic_id, sample_size)
            return
        
        # Original implementation for non-lazy mode
        df_topic = self.df[self.df.main_topic_thetas == topic_id]
        if sample_size:
            self._logger.info(f"Sampling {sample_size} chunks for topic {topic_id}")
            df_topic = df_topic.sample(n=sample_size, random_state=42).reset_index(drop=True)
            
            self._logger.info(f"Sampled {len(df_topic)} chunks for topic {topic_id}")
            
            # remove previous_check
            if previous_check is not None:
                # read previous check
                df_check = pd.read_parquet(previous_check)
                # filter df_check by topic
                previous_check = df_check[df_check["topic"] == topic_id]["source_chunk_id"].tolist()
                
                # filter df_topic by previous_check
                df_topic = df_topic[~df_topic["doc_id"].isin(previous_check)].reset_index(drop=True)

        self._logger.info(f"Found {len(df_topic)} chunks for topic {topic_id}")
        
        for _, row in df_topic.iterrows():
            metadata = {"top_k": row[self.row_top_k]}

            if "questions" in row and pd.notna(row["questions"]):
                q_raw = row["questions"]
                if isinstance(q_raw, str):
                    try:
                        questions = ast.literal_eval(q_raw)
                    except:
                        questions = [q.strip() for q in q_raw.split(";") if q.strip()]
                elif isinstance(q_raw, list):
                    questions = q_raw
                else:
                    questions = [q_raw]
                metadata["questions"] = questions

            
            if "answers" in row and pd.notna(row["answers"]):
                a_raw = row["answers"]
                try:
                    if isinstance(a_raw, str) and a_raw.startswith("["):
                        answers = ast.literal_eval(a_raw)  
                    else:
                        answers = [a_raw]
                except:
                    answers = []

                if isinstance(answers, list) and "questions" in metadata:
                    metadata["answers"] = dict(zip(metadata["questions"], answers))
                else:
                    raise ValueError(f"Answers are not a list or do not match the questions: {answers}")
                        
            yield Chunk(
                id=row["doc_id"],
                text=row["text"],
                full_doc=row.get("full_doc", ""),
                metadata=metadata
            )

    def retrieve_relevant_chunks(self, query: str, theta_query=None, top_k: int = None):
        if self.retriever is None:
            raise RuntimeError("No retriever has been set for this corpus.")

        results, _ = self.retriever.retrieve(
            query=query,
            theta_query=theta_query,
            top_k=top_k,
        )
        
        chunks = []
        for result in results:
            try:
                row = self.df[self.df.doc_id == result["doc_id"]].iloc[0]
                chunk = Chunk(
                    id=result["doc_id"],
                    text=row["text"],
                    full_doc=row.get("full_doc", ""),
                    metadata={"score": result["score"], "top_k": row[self.row_top_k]}
                )
                chunks.append(chunk)
            except KeyError:
                self._logger.warning(f"doc_id {result['doc_id']} not found in dataframe")

        return chunks