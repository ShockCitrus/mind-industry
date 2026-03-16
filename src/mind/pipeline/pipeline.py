import json
import re
import unicodedata
import threading
from collections import defaultdict
from pathlib import Path
from queue import Queue, Empty
from typing import List, Union, Tuple, Optional

import pandas as pd
import torch
from colorama import Fore, Style
from dotenv import dotenv_values
from mind.pipeline.corpus import Corpus
from mind.pipeline.retriever import IndexRetriever
from mind.pipeline.utils import extend_to_full_sentence
from mind.prompter.prompter import Prompter
from mind.utils.utils import init_logger, load_prompt, load_yaml_config_file, get_optimization_settings
import numpy as np
from sentence_transformers import SentenceTransformer  # type: ignore
from tqdm import tqdm  # type: ignore


class AsyncCheckpointer:
    """
    Background thread for non-blocking checkpoint writes.
    
    Queues DataFrames for writing and handles old file cleanup.
    Thread-safe for use from the main pipeline thread.
    """
    
    def __init__(self, logger=None):
        self._queue: Queue[Tuple[pd.DataFrame, Path, Optional[Path]]] = Queue()
        self._logger = logger
        self._running = True
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()
        self._pending_count = 0
        self._lock = threading.Lock()
    
    def _writer_loop(self):
        """Background loop that processes queued checkpoint writes."""
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
                if item is None:  # Shutdown signal
                    break
                    
                df, path, old_path = item
                
                try:
                    # Write checkpoint
                    df.to_parquet(path, index=False)
                    
                    # Clean up old checkpoint if it exists
                    if old_path and old_path.exists():
                        old_path.unlink()
                    
                    if self._logger:
                        self._logger.debug(f"Checkpoint saved: {path}")
                        
                except Exception as e:
                    if self._logger:
                        self._logger.error(f"Checkpoint write failed: {e}")
                finally:
                    self._queue.task_done()
                    with self._lock:
                        self._pending_count -= 1
                        
            except Empty:
                continue  # Timeout, check if still running
    
    def save_async(
        self, 
        df: pd.DataFrame, 
        path: Path, 
        old_path: Path = None
    ):
        """
        Queue a DataFrame for background saving.
        
        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to save (will be copied).
        path : Path
            Destination path for the Parquet file.
        old_path : Path, optional
            Previous checkpoint to delete after successful write.
        """
        with self._lock:
            self._pending_count += 1
        # Copy DataFrame to avoid race conditions with main thread
        self._queue.put((df.copy(), Path(path), Path(old_path) if old_path else None))
    
    def wait_complete(self, timeout: float = 60.0) -> bool:
        """
        Wait for all pending saves to complete.
        
        Parameters
        ----------
        timeout : float
            Maximum seconds to wait.
        
        Returns
        -------
        bool
            True if all writes completed, False if timeout.
        """
        try:
            self._queue.join()
            return True
        except Exception:
            return self._pending_count == 0
    
    def shutdown(self):
        """Stop the background writer thread cleanly."""
        self._running = False
        self._queue.put(None)  # Shutdown signal
        self._thread.join(timeout=5.0)
    
    @property
    def pending_writes(self) -> int:
        """Number of checkpoint writes still queued."""
        with self._lock:
            return self._pending_count




class MIND:
    """
    MIND pipeline class.

    =========================                
    All components are build based on the Prompter class. Each component has its own template and is responsible for generating the input for the next component.

    We apply additional non-LLM based filters:
    - Filter out yes/no questions
    - Check that the generated answer entails the original passage (if enabled)
    - If the target answer contains "I cannot answer the question", we directly label it as NOT_ENOUGH_INFO without checking for contradiction
    """

    def __init__(
        self,
        llm_model: str = None,
        llm_server: str = None,
        source_corpus: Union[Corpus, dict] = None,
        target_corpus: Union[Corpus, dict] = None,
        retrieval_method: str = "TB-ENN",
        multilingual: bool = True,
        monolingual: bool = False,
        lang: str = "en",
        config_path: Path = Path("/src/config/config.yaml"),
        logger=None,
        dry_run: bool = False,
        do_check_entailement: bool = False,
        env_path=None,
        selected_categories: list = None,
    ):
        self._monolingual = monolingual
        if monolingual:
            multilingual = False
        self._logger = logger if logger else init_logger(config_path, __name__)

        self.dry_run = dry_run
        self.retrieval_method = retrieval_method

        self.config = load_yaml_config_file(config_path, "mind", self._logger)
        self._embedding_model = self.config.get("embedding_models", {}).get("multilingual").get("model") if multilingual else self.config.get(
            "embedding_models", {}).get("monolingual").get(lang).get("model")
        self._do_norm = self.config.get("embedding_models", {}).get("multilingual").get("do_norm") if multilingual else self.config.get(
            "embedding_models", {}).get("monolingual").get(lang).get("do_norm")

        self.cannot_answer_dft = self.config.get(
            "cannot_answer_dft", "I cannot answer the question given the context.")
        self.cannot_answer_personal = self.config.get(
            "cannot_answer_personal", "I cannot answer the question since the context only contains personal opinions.")

        env_path = env_path or self.config.get(
            "llm", {}).get("gpt", {}).get("env_path")

        try:
            open_api_key = dotenv_values(env_path).get("OPEN_API_KEY", None)
        except Exception as e:
            self._logger.error(f"Failed to load environment variables: {e}")

        # Build Prompter: use explicit model if provided, otherwise fall back to
        # the llm.default block in config.yaml (Prompter.from_config).
        if llm_model:
            self._prompter = Prompter(
                model_type=llm_model,
                llm_server=llm_server,
                config_path=config_path,
                openai_key=open_api_key
            )
            self._prompter_answer = Prompter(
                model_type=llm_model,
                llm_server=llm_server,
                config_path=config_path,
                openai_key=open_api_key
            )
        else:
            self._logger.info(
                "No llm_model specified — using llm.default from config.yaml"
            )
            self._prompter = Prompter.from_config(
                config_path=config_path,
                llm_server=llm_server,
                logger=self._logger,
            )
            self._prompter_answer = Prompter.from_config(
                config_path=config_path,
                llm_server=llm_server,
                logger=self._logger,
            )
        self.prompts = {}
        for name in ["question_generation", "subquery_generation", "answer_generation", "contradiction_checking", "relevance_checking"]:
            path = self.config.get("prompts", {}).get(name)
            if path is None:
                raise ValueError(f"Missing prompt path for: {name}")
            self.prompts[name] = load_prompt(path)

        # --- Cost optimization settings (Strategies 1-7) ---
        cost_opt = self.config.get("cost_optimization", {})
        self._use_merged_evaluation = cost_opt.get("use_merged_evaluation", False)
        self._skip_subquery_generation = cost_opt.get("skip_subquery_generation", False)
        self._max_questions_per_chunk = cost_opt.get("max_questions_per_chunk", None)
        self._embedding_prefilter_threshold = cost_opt.get("embedding_prefilter_threshold", 0)
        self._relevance_method = cost_opt.get("relevance_method", "llm")
        self._retrieval_min_score_ratio = cost_opt.get("retrieval_min_score_ratio", 0)
        self._retrieval_max_k = cost_opt.get("retrieval_max_k", None)

        # Answer cache: keyed by (chunk_id, normalized_question) -> answer string
        self._answer_cache = {}

        # Load merged evaluation prompt if enabled
        if self._use_merged_evaluation:
            merged_path = self.config.get("prompts", {}).get("merged_evaluation")
            if merged_path is None:
                self._logger.warning(
                    "use_merged_evaluation=true but no merged_evaluation prompt path configured — "
                    "falling back to separate evaluation"
                )
                self._use_merged_evaluation = False
            else:
                self.prompts["merged_evaluation"] = load_prompt(merged_path)
                self._logger.info("Cost optimization: merged evaluation prompt loaded")

        if self._skip_subquery_generation:
            self._logger.info("Cost optimization: subquery generation disabled, using questions directly")
        if self._max_questions_per_chunk:
            self._logger.info(f"Cost optimization: max {self._max_questions_per_chunk} questions per chunk")

        # --- Dynamic category prompt ---
        if selected_categories:
            dynamic_path = self.config.get("prompts", {}).get("contradiction_checking_dynamic")
            if dynamic_path is None:
                self._logger.warning(
                    "No dynamic prompt path configured — falling back to static prompt"
                )
            else:
                dynamic_template = load_prompt(dynamic_path)
                categories_block, examples_block = self._build_category_prompt_sections(
                    selected_categories
                )
                # Pre-format the template with category/example blocks.
                # The {question}, {answer_1}, {answer_2} placeholders remain
                # for per-call formatting in _check_contradiction().
                self.prompts["contradiction_checking"] = dynamic_template.replace(
                    "{categories_block}", categories_block
                ).replace(
                    "{examples_block}", examples_block
                )
                self._logger.info(
                    f"[CAT] Dynamic prompt loaded with {len(selected_categories)} categories: "
                    + ", ".join(c['name'] for c in selected_categories)
                )
                # Log the full rendered prompt template (minus per-call placeholders)
                self._logger.info(
                    "[CAT] Rendered contradiction prompt template:\n"
                    + self.prompts["contradiction_checking"]
                )

            # Also format the dynamic merged evaluation prompt if enabled
            if self._use_merged_evaluation:
                merged_dynamic_path = self.config.get("prompts", {}).get("merged_evaluation_dynamic")
                if merged_dynamic_path:
                    merged_dynamic_template = load_prompt(merged_dynamic_path)
                    self.prompts["merged_evaluation"] = merged_dynamic_template.replace(
                        "{categories_block}", categories_block
                    ).replace(
                        "{examples_block}", examples_block
                    )
                    self._logger.info(
                        "[CAT] Dynamic merged evaluation prompt loaded"
                    )
                else:
                    self._logger.warning(
                        "No dynamic merged evaluation prompt path configured — "
                        "merged evaluation will use the static prompt"
                    )
        else:
            self._logger.info("[CAT] No categories selected — using static prompt (all 4 default categories)")

        # NLI components
        self._do_check_entailment = do_check_entailement
        if self._do_check_entailment:

            self._nli_model_name = self.config.get(
                "nli_model_name", "potsawee/deberta-v3-large-mnli")
            try:
                from transformers import (  # type: ignore
                    AutoModelForSequenceClassification, AutoTokenizer)
                self._nli_tokenizer = AutoTokenizer.from_pretrained(
                    self._nli_model_name, use_fast=False)
                self._nli_model = AutoModelForSequenceClassification.from_pretrained(
                    self._nli_model_name)
                self._logger.info(f"NLI model loaded: {self._nli_model_name}")
            except Exception as e:
                self._logger.error(f"Failed to load NLI model/tokenizer: {e}")
                self._nli_tokenizer, self._nli_model = None, None

        if source_corpus:
            self.source_corpus = self._init_corpus(
                source_corpus, is_target=False)
        if target_corpus:
            self.target_corpus = self._init_corpus(
                target_corpus, is_target=True)

        if self.dry_run:
            self._logger.warning(
                "Dry run mode is ON — no LLM calls will be made.")

        self.results = []
        self.discarded = []

        # keep a unique identifier for the questions generated per topic
        self.questions_id = defaultdict(set)

        # keep track of seen (question, source_chunk.id, target_chunk.id) triplets to avoid duplicates
        self.seen_triplets = set()

        # OPT-004: Load optimization settings and initialize async checkpointer if enabled
        self._opt_settings = get_optimization_settings(str(config_path), self._logger)
        self._async_checkpoints = self._opt_settings.get("async_checkpoints", True)
        if self._async_checkpoints:
            self._checkpointer = AsyncCheckpointer(logger=self._logger)
            self._logger.info("Async checkpointing enabled")
        else:
            self._checkpointer = None

    def _init_corpus(
        self,
        corpus: Union[Corpus, dict],
        is_target: bool = False,
    ) -> Corpus:

        if isinstance(corpus, Corpus):
            return corpus

        required_keys = {"corpus_path", "id_col",
                         "passage_col", "full_doc_col"}

        if not required_keys.issubset(corpus.keys()):
            raise ValueError(
                f"Missing keys in corpus config dict: {required_keys - corpus.keys()}")

        corpus_obj = Corpus.from_parquet_and_thetas(
            path_parquet=corpus["corpus_path"],
            path_thetas=Path(corpus["thetas_path"]) if corpus.get(
                "thetas_path") else None,
            id_col=corpus["id_col"],
            passage_col=corpus["passage_col"],
            full_doc_col=corpus["full_doc_col"],
            row_top_k=corpus.get("row_top_k", "top_k"),
            language_filter=corpus.get("language_filter", None),
            logger=self._logger,
            load_thetas=corpus.get("load_thetas", False),
            filter_ids=corpus.get("filter_ids", None)
        )

        self._logger.info(
            f"Corpus {corpus['corpus_path']} loaded with {len(corpus_obj.df)} documents.")

        if is_target:
            retriever = IndexRetriever(
                model=SentenceTransformer(self._embedding_model),
                logger=self._logger,
                top_k=self.config.get("top_k", 10),
                batch_size=self.config.get("batch_size", 32),
                min_clusters=self.config.get("min_clusters", 8),
                do_weighting=self.config.get("do_weighting", True),
                nprobe_fixed=self.config.get("nprobe_fixed", False),

            )
            retriever.build_or_load_index(
                source_path=corpus["corpus_path"],
                thetas_path=corpus["thetas_path"],
                save_path_parent=corpus["index_path"],
                method=corpus.get("method", "TB-ENN"),
                col_to_index=corpus["passage_col"],
                col_id=corpus["id_col"],
                lang=corpus.get("language_filter", None),
                load_thetas=corpus.get("load_thetas", False)
            )
            corpus_obj.retriever = retriever

        return corpus_obj

    def run_pipeline(self, topics, sample_size=None, previous_check=None, path_save="mind_results.parquet"):

        #  ensure path_save directory exists
        Path(path_save).mkdir(parents=True, exist_ok=True)

        for topic in topics:
            self._process_topic(
                topic, path_save, previous_check=previous_check, sample_size=sample_size)


        # OPT-004: Wait for all async checkpoints to complete before returning
        if self._checkpointer:
            pending = self._checkpointer.pending_writes
            if pending > 0:
                self._logger.info(f"Waiting for {pending} pending checkpoints...")
                self._checkpointer.wait_complete()
                self._logger.info("All checkpoints saved")

        # Final flush: write any remaining results that never reached the 200-entry
        # checkpoint threshold. Without this, small runs produce an empty directory
        # and process_mind_results has nothing to consolidate into mind_results.parquet.
        if self.results:
            final_path = Path(f"{path_save}/results_topic_final_0.parquet")
            df_final = pd.DataFrame(self.results)
            df_discarded_final = pd.DataFrame(self.discarded) if self.discarded else pd.DataFrame()
            if self._checkpointer:
                self._checkpointer.save_async(df_final, final_path)
                if not df_discarded_final.empty:
                    self._checkpointer.save_async(
                        df_discarded_final,
                        Path(f"{path_save}/discarded_topic_final_0.parquet")
                    )
                self._checkpointer.wait_complete()
            else:
                df_final.to_parquet(final_path, index=False)
                if not df_discarded_final.empty:
                    df_discarded_final.to_parquet(
                        Path(f"{path_save}/discarded_topic_final_0.parquet"), index=False
                    )
            self._logger.info(f"Final flush: wrote {len(self.results)} results to {final_path}")
        else:
            self._logger.warning("Pipeline finished with zero results — mind_results.parquet will not be created.")

        # Cost optimization: log total LLM API call counts
        prompter_calls = getattr(self._prompter, 'total_calls', 0)
        prompter_answer_calls = getattr(self._prompter_answer, 'total_calls', 0)
        total_calls = prompter_calls + prompter_answer_calls
        self._logger.info(
            f"=== LLM CALL SUMMARY ===\n"
            f"  Prompter calls:        {prompter_calls}\n"
            f"  Answer prompter calls: {prompter_answer_calls}\n"
            f"  Total LLM API calls:   {total_calls}\n"
            f"  Total results:         {len(self.results)}\n"
            f"========================"
        )

        # Log per-step breakdown if instrumentation is enabled
        if hasattr(self._prompter, 'call_summary') and self._prompter._instrumentation:
            summary = self.total_call_summary
            self._logger.info(
                f"=== PER-STEP BREAKDOWN ===\n" +
                "\n".join(f"  {step:<25s} {count:>6d}" 
                          for step, count in sorted(summary["calls_by_step"].items(), key=lambda x: -x[1])) +
                f"\n========================="
            )

    @property
    def total_call_summary(self) -> dict:
        """Aggregate call summaries from both prompter instances."""
        s1 = self._prompter.call_summary
        s2 = self._prompter_answer.call_summary
        merged_by_step = dict(s1["calls_by_step"])
        for k, v in s2["calls_by_step"].items():
            merged_by_step[k] = merged_by_step.get(k, 0) + v
        return {
            "total_calls": s1["total_calls"] + s2["total_calls"],
            "calls_by_step": merged_by_step,
            "total_tokens_in": s1["total_tokens_in"] + s2["total_tokens_in"],
            "total_tokens_out": s1["total_tokens_out"] + s2["total_tokens_out"],
        }


    def _normalize(self, s: str) -> str:
        s = unicodedata.normalize("NFKC", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"^[\s\-\–\—\•\"'“”‘’«»]+", "", s)
        return s

    def _process_topic(self, topic, path_save, previous_check=None, sample_size=None):
        for chunk in tqdm(self.source_corpus.chunks_with_topic(
            topic_id=topic,
            sample_size=sample_size,
            previous_check=previous_check
        ), desc=f"Topic {topic}"):
            self._process_chunk(chunk, topic, path_save)

    def _process_chunk(self, chunk, topic, path_save):
        self._logger.info(f"Processing chunk {chunk.id} for topic {topic}")

        questions = chunk.metadata.get("questions")
        

        if questions:
            self._logger.info(
                f"Using preloaded questions from chunk {chunk.id}")
        else:
            questions, _ = self._generate_questions(chunk)
        if questions == []:
            print(
                f"{Fore.RED}No questions generated for chunk {chunk.id}{Style.RESET_ALL}")
            return

        # Strategy 5: Limit maximum questions per chunk
        if self._max_questions_per_chunk and len(questions) > self._max_questions_per_chunk:
            self._logger.info(
                f"Cost optimization: truncating {len(questions)} questions to {self._max_questions_per_chunk}")
            questions = questions[:self._max_questions_per_chunk]

        self._logger.info(f"Generated questions: {questions}\n")
        for question in questions:
            self._process_question(question, chunk, topic, path_save)

    def _process_question(self, question, source_chunk, topic, path_save):
        # generate answer in source language
        a_s = None
        answers = source_chunk.metadata.get("answers")
        if answers and isinstance(answers, dict):
            a_s = answers.get(question)

        # Strategy 7: Check answer cache before generating
        if not a_s:
            cache_key = (getattr(source_chunk, "id", None), self._normalize(question))
            a_s = self._answer_cache.get(cache_key)
            if a_s:
                self._logger.info(f"Using cached answer for chunk {source_chunk.id}")

        if not a_s:
            a_s, _ = self._generate_answer(question, source_chunk)
            self._logger.info(f"Generated original answer: {a_s}\n")

            # Strategy 7: Cache the generated answer
            cache_key = (getattr(source_chunk, "id", None), self._normalize(question))
            self._answer_cache[cache_key] = a_s

            # check that the answer entails the original chunk
            # if not, discard the question
            if self._do_check_entailment:
                _, _, entails = self._check_entailement(a_s, source_chunk.text)
                if not entails or "cannot answer the question" in a_s.lower():
                    print(f"{Fore.RED}Discarding question '{question}' since the answer does not entail the original passage.{Style.RESET_ALL}\n ANSWER: {a_s}\nPASSAGE: {source_chunk.text}\n")
                    # self._logger.info(f"Discarding question '{question}' since the answer does not entail the original passage.\n ANSWER: {a_s}\nPASSAGE: {source_chunk.text}\n")
                    self.discarded.append({
                        "topic": topic,
                        "question": question,
                        "source_chunk": source_chunk.text,
                        "a_s": a_s,
                        "reason": "Answer does not entail the original passage"
                    })
                    return
        else:
            self._logger.info(
                f"Using preloaded answer from chunk {source_chunk.id}: {a_s}\n")

        # Strategy 2: Skip subquery generation if configured
        if self._skip_subquery_generation:
            # Use the question itself as the retrieval query
            retrieval_queries = self._get_retrieval_queries(question, source_chunk)
            self._logger.info(f"Cost optimization: using direct retrieval queries: {retrieval_queries}\n")
        else:
            # Original behavior: generate subqueries via LLM
            retrieval_queries, _ = self._generate_subqueries(question, source_chunk)
            self._logger.info(f"Generated subqueries: {retrieval_queries}\n")

        # generate answer in target language for each subquery and target chunk
        all_target_chunks = []
        for subquery in retrieval_queries:
            target_chunks = self.target_corpus.retrieve_relevant_chunks(
                query=subquery, theta_query=source_chunk.metadata["top_k"],
                top_k=self._retrieval_max_k)  # Strategy 6: respect retrieval_max_k config
            all_target_chunks.extend(target_chunks)
        # remove duplicates by chunk.id
        len_target_chunks = len(all_target_chunks)
        unique_target_chunks = {}
        for tc in all_target_chunks:
            if tc.id not in unique_target_chunks:
                unique_target_chunks[tc.id] = tc
        all_target_chunks = list(unique_target_chunks.values())
        self._logger.info(
            f"Retrieved {len_target_chunks} target chunks, {len(all_target_chunks)} unique.")

        # Strategy 6: Score-ratio cutoff — drop chunks whose retrieval score
        # is below (ratio × best_score). Reduces weak matches entering the loop.
        if self._retrieval_min_score_ratio > 0 and all_target_chunks:
            scores = [tc.metadata.get("score", 0) for tc in all_target_chunks]
            max_score = max(scores) if scores else 1.0
            cutoff = self._retrieval_min_score_ratio * max_score
            pre_count = len(all_target_chunks)
            all_target_chunks = [
                tc for tc in all_target_chunks
                if tc.metadata.get("score", 0) >= cutoff
            ]
            self._logger.info(
                f"Cost optimization: score-ratio cutoff ({self._retrieval_min_score_ratio}×{max_score:.3f}={cutoff:.3f}) "
                f"kept {len(all_target_chunks)}/{pre_count} chunks")

        # Strategy 3: Embedding-based pre-filter
        if self._embedding_prefilter_threshold > 0:
            pre_count = len(all_target_chunks)
            all_target_chunks = self._prefilter_target_chunks(
                question, all_target_chunks, self._embedding_prefilter_threshold)
            self._logger.info(
                f"Cost optimization: embedding pre-filter kept {len(all_target_chunks)}/{pre_count} chunks")

        for target_chunk in all_target_chunks:
            src_id = getattr(source_chunk, "id", None)
            tgt_id = getattr(target_chunk, "id", None)

            # Monolingual self-exclusion: skip comparing a chunk against itself
            if self._monolingual and src_id is not None and src_id == tgt_id:
                self._logger.info(
                    f"Monolingual self-exclusion: skipping target chunk {tgt_id} (same as source)")
                continue

            qkey = self._normalize(question)

            triplet = (qkey, src_id, tgt_id)
            if triplet in self.seen_triplets:
                continue
            self.seen_triplets.add(triplet)

            # Use the first retrieval query as the reported subquery
            reported_subquery = retrieval_queries[0] if retrieval_queries else question

            # Strategy 1: Use merged evaluation if configured
            if self._use_merged_evaluation:
                self._evaluate_pair_merged(question, a_s, source_chunk,
                                           target_chunk, topic, reported_subquery, path_save)
            else:
                self._evaluate_pair(question, a_s, source_chunk,
                                    target_chunk, topic, reported_subquery, path_save)

    def _filter_bad_questions(self, questions: List[str]) -> List[str]:
        """Remove questions that are not well-formed or relevant.

        Parameters
        ----------
        questions : list[str]
            List of questions to filter.

        Returns
        -------
        list[str]
            Filtered list of questions.

        Filters applied
        ---------------
        1) Keep only yes/no style questions, trimming any preamble.
        2) Structural filters: must end with '?', have at least 3 words,
        and not start with follow-up openers like "and", "but", "or", "so".
        3) Remove questions that reference studies, reports, documents, sections, or
        sample-specific phrases, including participle phrasing like
        "results indicated..." or "the report summarized...".
        """

        # yes/no auxiliary verbs
        _aux = (
            "is", "are", "am", "was", "were",
            "do", "does", "did",
            "has", "have", "had",
            "can", "could",
            "will", "would",
            "shall", "should",
            "may", "might",
            "must"
        )
        _aux_re = re.compile(rf"^\W*(?:{'|'.join(_aux)})\b", re.IGNORECASE)

        # follow-up openers
        _followup_openers = ("and", "but", "or", "so")

        # study/doc/sample-like phrases
        _DOC = (
            r"(?:study|survey|report|document|guidance|paper|article|memo|white\s*paper|brief|"
            r"dataset|discussion|section|appendix|table|figure|results?)"
        )
        _VERB = (
            r"(?:include|mention|provide|state|say|note|discuss|address|cover|contain|list|"
            r"describe|reference|present|report|indicate|summarize|focus)"
        )
        _PART = (
            r"(?:included|mentioned|provided|stated|noted|discussed|addressed|covered|contained|"
            r"listed|described|referenced|presented|reported|indicated|summarized|focused)"
        )

        _P1 = rf"\baccording to (?:the |this |that )?(?:results?|{_DOC})\b"
        _P2 = rf"\b(?:do|does|did|has|have|had)\s+(?:(?:the|this|that|these|those)\s+)?{_DOC}\s+{_VERB}\b"
        _P3 = rf"\b(?:in|within|from)\s+(?:(?:the|this|that)\s+)?{_DOC}\b"
        _P4 = rf"\b(?:selected|surveyed|polled|sampled|enrolled)\s+(?:respondents?|participants?|subjects?)\b"
        _P5 = rf"\bdid\s+(?:the\s+)?(?:study|survey)\b"
        _P6 = rf"\bresults?\b.*\b{_PART}\b|\b{_DOC}\b.*\b{_PART}\b"

        _study_like_re = re.compile(
            rf"(?:{_P1}|{_P2}|{_P3}|{_P4}|{_P5}|{_P6})", re.IGNORECASE)

        kept = []
        for q in questions:
            if not isinstance(q, str) or not q.strip():
                continue
            qn = self._normalize(q)

            m = _aux_re.match(qn)
            if not m:
                continue

            # Trim any junk before the auxiliary
            qn = qn[m.start():]

            # Structural checks
            if not qn.endswith("?"):
                continue
            if len(qn.split()) < 3:
                continue
            if qn.lower().startswith(_followup_openers):
                continue

            # Study/doc/sample-like filters
            if _study_like_re.search(qn):
                continue

            kept.append(qn)

        return kept

    def _evaluate_pair(self, question, a_s, source_chunk, target_chunk, topic, subquery, path_save=None, save=True):
        # Strategy 4: Use configured relevance method
        if self._relevance_method == "embedding":
            # Use retrieval score as a proxy for relevance (no LLM call)
            score = target_chunk.metadata.get("score", 0)
            is_relevant = 1 if score > 0.3 else 0
            self._logger.info(f"Embedding relevance: score={score:.3f} → relevant={is_relevant}")
        else:
            # Default: LLM-based relevance check
            is_relevant, _ = self._check_is_relevant(question, target_chunk)

        if is_relevant == 0:
            a_t = self.cannot_answer_dft
        else:
            a_t, _ = self._generate_answer(question, target_chunk)

        if "cannot answer the question" in a_t.lower():
            discrepancy_label = "NOT_ENOUGH_INFO"
            reason = self.cannot_answer_dft
        elif "cannot answer" in a_t.lower() or "personal opinion" in a_t.lower():
            discrepancy_label = "NOT_ENOUGH_INFO"
            reason = self.cannot_answer_personal
        else:
            discrepancy_label, reason = self._check_contradiction(
                question, a_s, a_t)

        # if discrepancy_label in ["CONTRADICTION", "CULTURAL_DISCREPANCY", "NOT_ENOUGH_INFO", "NO_DISCREPANCY"]:
        self._log_contradiction(
            topic,
            source_chunk,
            target_chunk,
            question,
            a_s,
            a_t,
            discrepancy_label,
            reason
        )

        if save and path_save is not None:
            self._print_result(discrepancy_label, question, a_s,
                               a_t, reason, target_chunk.text, source_chunk.text)

            question_id = len(self.questions_id[topic])
            self.questions_id[topic].add(question_id)

            self.results.append({
                "topic": topic,
                "question_id": question_id,
                "question": question,
                "subquery": subquery,
                "source_chunk": source_chunk.text,
                "target_chunk": target_chunk.text,
                "a_s": a_s,
                "a_t": a_t,
                "label": discrepancy_label,
                "reason": reason,
                # add original metadata
                "source_chunk_id": getattr(source_chunk, "id", None),
                "target_chunk_id": getattr(target_chunk, "id", None),
            })
            # save results every 200 entries
            if len(self.results) % 200 == 0:

                checkpoint = len(self.results) // 200
                results_checkpoint_path = Path(
                    f"{path_save}/results_topic_{topic}_{checkpoint}.parquet")
                discarded_checkpoint_path = Path(
                    f"{path_save}/discarded_topic_{topic}_{checkpoint}.parquet")

                df = pd.DataFrame(self.results)
                df_discarded = pd.DataFrame(self.discarded)

                # OPT-004: Use async checkpointing if available
                old_results_checkpoint_path = Path(
                    f"{path_save}/results_topic_{topic}_{checkpoint-1}.parquet")
                old_discarded_checkpoint_path = Path(
                    f"{path_save}/discarded_topic_{topic}_{checkpoint-1}.parquet")

                if self._checkpointer:
                    # Async write (non-blocking)
                    self._checkpointer.save_async(df, results_checkpoint_path, old_results_checkpoint_path)
                    self._checkpointer.save_async(df_discarded, discarded_checkpoint_path, old_discarded_checkpoint_path)
                else:
                    # Sync write (original behavior)
                    df.to_parquet(results_checkpoint_path, index=False)
                    df_discarded.to_parquet(discarded_checkpoint_path, index=False)
                    if old_results_checkpoint_path.exists():
                        old_results_checkpoint_path.unlink()
                    if old_discarded_checkpoint_path.exists():
                        old_discarded_checkpoint_path.unlink()

        return a_t, discrepancy_label, reason

    def _evaluate_pair_merged(self, question, a_s, source_chunk, target_chunk, topic, subquery, path_save=None, save=True):
        """Strategy 1: Evaluate a source-target pair with a single merged LLM call.

        Replaces the 3-call sequence (relevance check + target answer + contradiction check)
        with one call that performs all three tasks simultaneously.
        """
        template_formatted = self.prompts["merged_evaluation"].format(
            question=question,
            answer_s=a_s,
            target_passage=target_chunk.text,
        )

        response, _ = self._prompter.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter.log_call("merged_evaluation")

        if self.dry_run:
            a_t = response
            discrepancy_label = response
            reason = ""
        else:
            a_t, discrepancy_label, reason = self._parse_merged_response(response)

            # Defensive short-circuit: match _evaluate_pair behavior for "cannot answer"
            if "cannot answer the question" in a_t.lower():
                discrepancy_label = "NOT_ENOUGH_INFO"
                reason = self.cannot_answer_dft
            elif "cannot answer" in a_t.lower() or "personal opinion" in a_t.lower():
                discrepancy_label = "NOT_ENOUGH_INFO"
                reason = self.cannot_answer_personal

        # Log result
        self._log_contradiction(
            topic, source_chunk, target_chunk, question, a_s, a_t,
            discrepancy_label, reason
        )

        if save and path_save is not None:
            self._print_result(discrepancy_label, question, a_s,
                               a_t, reason, target_chunk.text, source_chunk.text)

            question_id = len(self.questions_id[topic])
            self.questions_id[topic].add(question_id)

            self.results.append({
                "topic": topic,
                "question_id": question_id,
                "question": question,
                "subquery": subquery,
                "source_chunk": source_chunk.text,
                "target_chunk": target_chunk.text,
                "a_s": a_s,
                "a_t": a_t,
                "label": discrepancy_label,
                "reason": reason,
                "source_chunk_id": getattr(source_chunk, "id", None),
                "target_chunk_id": getattr(target_chunk, "id", None),
            })
            # save results every 200 entries (same checkpoint logic as _evaluate_pair)
            if len(self.results) % 200 == 0:
                checkpoint = len(self.results) // 200
                results_checkpoint_path = Path(
                    f"{path_save}/results_topic_{topic}_{checkpoint}.parquet")
                discarded_checkpoint_path = Path(
                    f"{path_save}/discarded_topic_{topic}_{checkpoint}.parquet")

                df = pd.DataFrame(self.results)
                df_discarded = pd.DataFrame(self.discarded)

                old_results_checkpoint_path = Path(
                    f"{path_save}/results_topic_{topic}_{checkpoint-1}.parquet")
                old_discarded_checkpoint_path = Path(
                    f"{path_save}/discarded_topic_{topic}_{checkpoint-1}.parquet")

                if self._checkpointer:
                    self._checkpointer.save_async(df, results_checkpoint_path, old_results_checkpoint_path)
                    self._checkpointer.save_async(df_discarded, discarded_checkpoint_path, old_discarded_checkpoint_path)
                else:
                    df.to_parquet(results_checkpoint_path, index=False)
                    df_discarded.to_parquet(discarded_checkpoint_path, index=False)
                    if old_results_checkpoint_path.exists():
                        old_results_checkpoint_path.unlink()
                    if old_discarded_checkpoint_path.exists():
                        old_discarded_checkpoint_path.unlink()

        return a_t, discrepancy_label, reason

    def _parse_merged_response(self, response):
        """Parse the merged evaluation LLM response.

        Extracts TARGET_ANSWER, REASON, and DISCREPANCY_TYPE from a single
        merged response. Falls back to regex if structured parsing fails.

        Returns
        -------
        tuple
            (target_answer, discrepancy_label, reason)
        """
        self._logger.info("-" * 40)
        self._logger.info("MERGED EVAL RAW RESPONSE:")
        self._logger.info(response)
        self._logger.info("-" * 40)

        target_answer = None
        reason = None
        label = None

        # Line-based parsing
        lines = response.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("TARGET_ANSWER:"):
                target_answer = stripped[len("TARGET_ANSWER:"):].strip()
            elif stripped.startswith("DISCREPANCY_TYPE:"):
                label = stripped[len("DISCREPANCY_TYPE:"):].strip()
            elif stripped.startswith("REASON:"):
                reason = stripped[len("REASON:"):].strip()

        # Fallback: regex scan
        if target_answer is None:
            m = re.search(r"TARGET_ANSWER:\s*(.+?)(?:\n|REASON:|DISCREPANCY_TYPE:|$)", response, re.DOTALL)
            if m:
                target_answer = m.group(1).strip()
        if label is None:
            m = re.search(r"DISCREPANCY_TYPE:\s*(\S+)", response)
            if m:
                label = m.group(1).strip()
        if reason is None:
            m = re.search(r"REASON:\s*(.+?)(?:\n|TARGET_ANSWER:|DISCREPANCY_TYPE:|$)", response, re.DOTALL)
            if m:
                reason = m.group(1).strip()

        # Defaults
        if target_answer is None or target_answer.upper() == "N/A":
            target_answer = self.cannot_answer_dft
        if label is None:
            label = response
        if reason is None:
            reason = ""

        label = self._clean_contradiction(label)

        self._logger.info(f"[MERGED] PARSED → a_t={target_answer[:60]!r}  label={label!r}  reason={reason[:80]!r}")
        return target_answer, label, reason

    def _get_retrieval_queries(self, question: str, chunk) -> list:
        """Strategy 2: Derive retrieval queries without LLM calls.

        Uses the question itself as the primary retrieval query.
        No LLM call needed — the sentence-transformer embeddings handle
        semantic similarity well with natural-language questions.

        Returns
        -------
        list[str]
            One or two retrieval queries derived from the question.
        """
        queries = [question]
        return queries

    def _prefilter_target_chunks(self, question: str, target_chunks: list, threshold: float = 0.3) -> list:
        """Strategy 3: Filter target chunks by embedding similarity before LLM calls.

        Uses the retriever's encoder to compute cosine similarity between
        the question and each target chunk, removing obviously irrelevant pairs.

        Parameters
        ----------
        question : str
            The question to check relevance against.
        target_chunks : list
            List of Chunk objects to filter.
        threshold : float
            Minimum cosine similarity to keep a chunk.

        Returns
        -------
        list
            Filtered list of chunks above the similarity threshold.
        """
        if not hasattr(self.target_corpus, 'retriever') or self.target_corpus.retriever is None:
            return target_chunks  # Cannot filter without retriever

        try:
            question_embedding = self.target_corpus.retriever.encode_queries(question)
            if question_embedding.ndim > 1:
                question_embedding = question_embedding.flatten()

            filtered = []
            for chunk in target_chunks:
                # Encode the chunk text for comparison
                chunk_embedding = self.target_corpus.retriever.encode_queries(chunk.text)
                if chunk_embedding.ndim > 1:
                    chunk_embedding = chunk_embedding.flatten()

                similarity = float(np.dot(question_embedding, chunk_embedding))
                if similarity >= threshold:
                    filtered.append(chunk)
                else:
                    self._logger.info(
                        f"Pre-filtered chunk {chunk.id} (sim={similarity:.3f} < {threshold})")

            return filtered
        except Exception as e:
            self._logger.warning(f"Embedding pre-filter failed: {e} — keeping all chunks")
            return target_chunks

    def _print_result(self, label, question, a_s, a_t, reason, target_text, source_text):
        color_map = {
            "CONTRADICTION": Fore.RED,
            "CULTURAL_DISCREPANCY": Fore.MAGENTA,
            "NOT_ENOUGH_INFO": Fore.YELLOW,
            "AGREEMENT": Fore.GREEN,
            "NO_DISCREPANCY": Fore.GREEN,
        }
        # Default to a bright purple (ANSI 135) for custom categories
        color = color_map.get(label, "\033[38;5;135m")

        print()
        print(
            f"{color}{Style.BRIGHT}== DISCREPANCY DETECTED: {label} =={Style.RESET_ALL}")
        print(f"{Fore.BLUE}Source Chunk Text:{Style.RESET_ALL} {source_text}")
        print(f"{Fore.BLUE}Question:{Style.RESET_ALL} {question}")
        print(f"{Fore.GREEN}Original Answer:{Style.RESET_ALL} {a_s}")
        print(f"{Fore.RED}Target Answer:{Style.RESET_ALL} {a_t}")
        print(f"{Fore.CYAN}Reason:{Style.RESET_ALL} {reason}")
        print(f"{Fore.YELLOW}Target Chunk Text:{Style.RESET_ALL} {target_text}")
        print()

    def _generate_questions(self, chunk):
        template_formatted = self.prompts["question_generation"].format(
            passage=chunk.text,
            full_document=extend_to_full_sentence(
                chunk.full_doc, 100) + " [...]",
        )

        response, _ = self._prompter.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter.log_call("question_generation")
        if self.dry_run:
            return [response], ""

        if "N/A" in response:
            return [], response

        try:
            for sep in ["\n", ","]:
                if sep in response:
                    questions = [
                        q.strip() for q in response.split(sep)
                        if q.strip() and "passage" not in q
                    ]
                    # remove
                    len_q = len(questions)
                    questions = self._filter_bad_questions(questions)
                    self._logger.info(
                        f"Filtered out {len_q - len(questions)} / {len_q} NO yes/no questions.")

                    return questions, ""
            return [], "No valid separator found"

        except Exception as e:
            self._logger.error(f"Error parsing questions: {e}")
            return [], str(e)

    def _generate_subqueries(self, question, chunk):
        try:
            template_formatted = self.prompts["subquery_generation"].format(
                question=question,
                passage=chunk.text,
            )
        except KeyError as e:
            self._logger.error(f"Missing field in subquery template: {e}")
            return [], str(e)

        response, _ = self._prompter.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter.log_call("subquery_generation")

        if self.dry_run:
            return [response], ""

        try:
            queries = [el.strip() for el in response.split(";") if el.strip()]
            return queries, ""
        except Exception as e:
            self._logger.error(f"Error extracting subqueries: {e}")
            return [], str(e)

    def retrieve_relevant_chunks(self, subquery: str, chunk):
        if self.dry_run:
            return []

        return self.target_corpus.retrieve_relevant_chunks(
            query=subquery,
            theta_query=chunk.top_k,
        )

    def _generate_answer(self, question, chunk):
        template_formatted = self.prompts["answer_generation"].format(
            question=question,
            passage=chunk.text,
            full_document=(extend_to_full_sentence(
                chunk.full_doc, 100) + " [...]")
        )

        response, _ = self._prompter_answer.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter_answer.log_call("answer_generation")

        if self.dry_run:
            return response, ""

        return response, ""

    def _check_is_relevant(self, question, chunk):
        template_formatted = self.prompts["relevance_checking"].format(
            passage=chunk.text,
            question=question
        )

        response, _ = self._prompter.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter.log_call("relevance_check")

        if self.dry_run:
            return response, ""

        relevance = 1 if "yes" in response.lower() else 0

        return relevance, response

    def _check_contradiction(self, question, answer_s, answer_t):
        template_formatted = self.prompts["contradiction_checking"].format(
            question=question,
            answer_1=answer_s,
            answer_2=answer_t
        )

        # Log full prompt sent to LLM
        self._logger.info("[CAT] PROMPT SENT TO LLM:\n" + template_formatted)

        response, _ = self._prompter.prompt(
            question=template_formatted,
            dry_run=self.dry_run
        )
        self._prompter.log_call("contradiction_check")

        if self.dry_run:
            return response, ""

        # --- Debug log for raw response ---
        self._logger.info("-" * 40)
        self._logger.info("RAW LLM RESPONSE:")
        self._logger.info(response)
        self._logger.info("-" * 40)

        label, reason = None, None
        lines = response.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("DISCREPANCY_TYPE:"):
                label = stripped[len("DISCREPANCY_TYPE:"):].strip()
            elif stripped.startswith("REASON:"):
                reason = stripped[len("REASON:"):].strip()

        # Fallback: regex scan the whole response
        if label is None:
            m = re.search(r"DISCREPANCY_TYPE:\s*(\S+)", response)
            if m:
                label = m.group(1).strip()
        if reason is None:
            m = re.search(r"REASON:\s*(.+?)(?:\n|DISCREPANCY_TYPE:|$)", response, re.DOTALL)
            if m:
                reason = m.group(1).strip()

        # Last resort
        if label is None:
            label = response
        if reason is None:
            reason = ""

        self._logger.info(f"[CAT] PARSED → label={label!r}  reason={reason[:80]!r}")
        return self._clean_contradiction(label), reason

    def _clean_contradiction(self, discrepancy_label):
        """Normalize raw LLM output to SCREAMING_SNAKE_CASE.
        Caps at 40 chars — anything longer is a parse failure."""
        label = discrepancy_label.strip().upper()
        label = re.sub(r'[^A-Z0-9_]', '_', label)
        label = re.sub(r'_+', '_', label).strip('_')
        if len(label) > 40:
            label = "PARSE_ERROR"
        return label

    def _build_category_prompt_sections(self, selected_categories: list) -> tuple:
        """Build the categories_block and examples_block for the NLI prompt."""
        categories_block_lines = []
        examples_block_lines = ["#### EXAMPLES ####", ""]

        for i, cat in enumerate(selected_categories, 1):
            categories_block_lines.append(
                f"{i}. {cat['name']}: {cat['prompt_instruction']}"
            )
            categories_block_lines.append("")

            if cat.get('examples'):
                examples = (
                    json.loads(cat['examples'])
                    if isinstance(cat['examples'], str)
                    else cat['examples']
                )
                for ex in examples:
                    examples_block_lines.append(f"QUESTION: {ex['question']}")
                    examples_block_lines.append(f"ANSWER_1: {ex['answer_1']}")
                    examples_block_lines.append(f"ANSWER_2: {ex['answer_2']}")
                    examples_block_lines.append(f"REASON: {ex['reason']}")
                    examples_block_lines.append(f"DISCREPANCY_TYPE: {ex['expected_label']}")
                    examples_block_lines.append("")

        return "\n".join(categories_block_lines), "\n".join(examples_block_lines)

    def _check_entailement(self, textA, textB, threshold=0.5):
        """
        Compute textual entailment between (textA -> textB) using a 2-class MNLI head.

        Returns:
            entail_prob (float), contradict_prob (float), entails_bool (bool)
        """
        if self._nli_tokenizer is None or self._nli_model is None:
            self._logger.error("NLI tokenizer/model not available.")
            return 0.0, 0.0, False

        try:
            inputs = self._nli_tokenizer.batch_encode_plus(
                batch_text_or_text_pairs=[(textA, textB)],
                add_special_tokens=True,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            with torch.no_grad():
                # neutral already removed (2 classes)
                logits = self._nli_model(**inputs).logits
                # [P(entail), P(contradict)]
                probs = torch.softmax(logits, dim=-1)[0]
                entail_prob = float(probs[0].item())
                contradict_prob = float(probs[1].item())
                entails = entail_prob >= threshold
            return entail_prob, contradict_prob, entails
        except Exception as e:
            self._logger.error(f"Entailment check failed: {e}")
            return 0.0, 0.0, False

    def _log_contradiction(self, topic, source_chunk, target_chunk, question, source_answer, target_answer, discrepancy_label, reason):
        self._logger.info({
            "topic": topic,
            "source_chunk_id": getattr(source_chunk, "id", None),
            "target_chunk_id": getattr(target_chunk, "id", None),
            "question": question,
            "original_answer": source_answer,
            "target_answer": target_answer,
            "discrepancy_label": discrepancy_label,
            "reason": reason
        })
