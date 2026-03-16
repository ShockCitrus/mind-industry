"""Python wrapper for the LDA Mallet Topic Model to train a topic model for each language in a corpus of documents.

The input to the LDA Mallet Topic Model is a corpus of documents in the same format as for the PolylingualTM wrapper, but each language is treated as a separate corpus to be modeled independently. The output is a folder with the following structure:

- model_folder
|--- train_data
|    |--- corpus_lang1.txt
|    |--- corpus_lang2.txt
|--- mallet_input
|    |--- corpus_lang1.mallet
|    |--- corpus_lang2.mallet
|--- mallet_output_lang1
|    |--- doc-topics.txt
|--- mallet_output_lang2
|    |--- doc-topics.txt
"""

import logging
import pathlib
from subprocess import check_output
from typing import List
import pandas as pd
import os
import shutil
import numpy as np
from sklearn.preprocessing import normalize
from scipy import sparse
from mind.utils.utils import file_lines
import shutil as _shutil
import warnings

class LDATM(object):
    def __init__(
        self,
        langs: list,
        model_folder: str,
        num_topics: int = 35,
        alpha: float = 5.0,
        optimize_interval: int = 10,
        num_threads: int = 4,
        num_iterations: int = 1000,
        doc_topic_thr: float = 0.0,
        token_regexp: str = "[\p{L}\p{N}][\p{L}\p{N}\p{P}]*\p{L}",
        thetas_thr=0.003,
        mallet_path: str = "src/topic_modeling/Mallet-202108/bin/mallet",
        logger: logging.Logger = None,
        load_existing: bool = False
    ) -> None:
        """Initialize the LDATM object.

        Parameters
        ----------
        langs : list
            List of languages to be modeled.
        model_folder : str
            The folder where all information related to the model will be stored.
        num_topics : int
            The number of topics to extract.
        alpha : float
            The alpha hyperparameter for the model.
        optimize_interval: int
            The interval for optimizing hyperparameters.
        num_threads: int
            The number of threads to use.
        num_iterations: int
            The number of iterations to run.
        doc_topic_thr: float
            The threshold for the document-topic distribution.
        token_regexp : str
            The regular expression to use for tokenization.
        mallet_path : str
            The path to the Mallet executable.
        logger : logging.Logger
            A logger object to log messages.
        load_existing : bool
            If True, load an existing model from the model folder.
        """
        self._langs = langs
        self._num_topics = num_topics
        self._alpha = alpha
        self._optimize_interval = optimize_interval
        self._num_threads = num_threads
        self._num_iterations = num_iterations
        self._doc_topic_thr = doc_topic_thr
        self._token_regexp = token_regexp
        self._thetas_thr = thetas_thr
        self._model_folder = model_folder
        self._mallet_path = pathlib.Path(mallet_path)

        if logger:
            self._logger = logger
        else:
            logging.basicConfig(level='INFO')
            self._logger = logging.getLogger('LDATM')
            # Add a console handler to output logs to the console
            console_handler = logging.StreamHandler()
            # Set handler level to INFO or lower
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        # Create folder for the model
        # If a model with the same name already exists, save a copy; then create a new folder
        if self._model_folder.exists():
            if not load_existing:
                self._logger.info(
                    f"-- -- Given model folder {self._model_folder} already exists. Saving a copy ..."
                )
                old_model_folder = self._model_folder.parent / \
                    (self._model_folder.name + "_old")
                if not old_model_folder.is_dir():
                    os.makedirs(old_model_folder)
                    shutil.move(self._model_folder, old_model_folder)
                self._model_folder.mkdir(exist_ok=True)
        else:
            self._model_folder.mkdir(parents=True, exist_ok=True)

        self._model_folder.mkdir(exist_ok=True)

        return
    
    @classmethod
    def load_model(cls, model_folder: str, langs: List[str], **kwargs):
        """
        Loads an existing LDATM model from disk. Assumes the folder structure is intact.
        """
        return cls(
            langs=langs,
            model_folder=model_folder,
            **kwargs
        )


    def _create_mallet_input_corpus(self, df_path: pathlib.Path) -> int:
        self._train_data_folder = self._model_folder / "train_data"
        self._train_data_folder.mkdir(exist_ok=True)

        df = pd.read_parquet(df_path)

        for lang in self._langs:
            df_lang = df[df.lang == lang]
            if df_lang.empty:
                self._logger.error(f"-- -- No documents found for language {lang}.")
                return 1

            corpus_txt_path = self._train_data_folder / f"corpus_{lang}.txt"
            self._logger.info(f"-- -- Creating Mallet {corpus_txt_path}...")

            with corpus_txt_path.open("w", encoding="utf8") as fout:
                for i, t in zip(df_lang.doc_id, df_lang.lemmas):
                    fout.write(f"{i} 0 {t}\n")

        return 2 if all((self._train_data_folder / f"corpus_{lang}.txt").exists() for lang in self._langs) else 0


    def _prepare_mallet_input(self) -> int:
        self._mallet_input_folder = self._model_folder / "mallet_input"
        self._mallet_input_folder.mkdir(exist_ok=True)

        for lang in self._langs:
            corpus_txt_path = self._train_data_folder / f"corpus_{lang}.txt"
            corpus_mallet = self._mallet_input_folder / f"corpus_{lang}.mallet"

            cmd = f'{self._mallet_path} import-file --preserve-case --keep-sequence --remove-stopwords ' \
                f'--token-regex "{self._token_regexp}" --print-output --input {corpus_txt_path} --output {corpus_mallet}'

            try:
                self._logger.info(f'-- -- Running command {cmd}')
                check_output(args=cmd, shell=True)
            except:
                self._logger.error('-- -- Mallet failed to import data. Revise command')
                return 0

        return 2 if all((self._mallet_input_folder / f"corpus_{lang}.mallet").exists() for lang in self._langs) else 1


    def train(
        self,
        df_path: pathlib.Path,
    ) -> int:
        """Assuming there is a 'corpus_es.mallet' and 'corpus_en.mallet' files in the model folder, trains two LDA Mallet Topic Models, one for each language in the corpus.

        Returns
        -------
        status : int
            Status of the operation:
            - 2 if the operation was successful.
            - 1 if the input files are missing.
            - 0 if the operation failed.
        """

        # Create the input files for Mallet
        self._create_mallet_input_corpus(df_path)

        # Prepare the input files for Mallet
        self._prepare_mallet_input()

        # Create folder for saving Mallet output
        self._mallet_out_folder = self._model_folder / "mallet_output"
        self._mallet_out_folder.mkdir(exist_ok=True)

        # Actual training of the model
        for lang in self._langs:

            # Get the training data
            mallet_input_file = \
                self._mallet_input_folder / f"corpus_{lang}.mallet"

            # Create folder for saving Mallet output for each language
            mallet_out_folder_lang = self._mallet_out_folder / f"{lang}"
            mallet_out_folder_lang.mkdir(exist_ok=True)

            # Create the Mallet configuration file
            config_mallet = mallet_out_folder_lang / f"config_{lang}.mallet"

            with config_mallet.open('w', encoding='utf8') as fout:
                fout.write(
                    'input = ' + mallet_input_file.resolve().as_posix() + '\n')
                fout.write('num-topics = ' + str(self._num_topics) + '\n')
                fout.write('alpha = ' + str(self._alpha) + '\n')
                fout.write('optimize-interval = ' +
                           str(self._optimize_interval) + '\n')
                fout.write('num-threads = ' + str(self._num_threads) + '\n')
                fout.write('num-iterations = ' +
                           str(self._num_iterations) + '\n')
                fout.write('doc-topics-threshold = ' +
                           str(self._doc_topic_thr) + '\n')
                fout.write('output-state = ' + mallet_out_folder_lang.joinpath(
                    'topic-state.gz').resolve().as_posix() + '\n')
                fout.write('output-doc-topics = ' +
                           mallet_out_folder_lang.joinpath('doc-topics.txt').resolve().as_posix() + '\n')
                fout.write('word-topic-counts-file = ' +
                           mallet_out_folder_lang.joinpath('word-topic-counts.txt').resolve().as_posix() + '\n')
                fout.write('diagnostics-file = ' +
                           mallet_out_folder_lang.joinpath('diagnostics.xml ').resolve().as_posix() + '\n')
                fout.write('xml-topic-report = ' +
                           mallet_out_folder_lang.joinpath('topic-report.xml').resolve().as_posix() + '\n')
                fout.write('output-topic-keys = ' +
                           mallet_out_folder_lang.joinpath('topickeys.txt').resolve().as_posix() + '\n')
                fout.write('inferencer-filename = ' +
                           mallet_out_folder_lang.joinpath('inferencer.mallet').resolve().as_posix() + '\n')

            cmd = self._mallet_path.as_posix() + \
                ' train-topics --config ' + str(config_mallet)

            try:
                self._logger.info(
                    f'-- -- Training LDA Mallet topic model. Command is {cmd}')
                check_output(args=cmd, shell=True)
            except:
                self._logger.error(
                    '-- -- Model training failed. Revise command')
                return
            
            self._get_more_info(mallet_out_folder_lang)
            self._extract_pipe() # Extract pipe for later inference

        # Create PolylingualTM-compatible output files so the rest of the
        # pipeline (detection, doc_representation, getTopicKeys) can consume
        # them without special-casing.
        self._create_compatible_outputs()

        return self._mallet_out_folder

    def _create_compatible_outputs(self):
        """
        Create PolylingualTM-compatible output files in the flat
        ``mallet_output/`` directory so that existing consumers
        (detection, doc_representation, getTopicKeys) work unchanged.

        Mapping for each language *lang*:
        - ``mallet_output/{lang}/thetas.npz``  →  ``mallet_output/thetas_{lang}.npz``
        - ``mallet_output/{lang}/topickeys.txt``  →  ``mallet_output/keys_{lang}.txt``
          (converted from Mallet "topic_id  alpha  word1 word2 …" to one-line-per-topic
          space-separated word list, matching PolylingualTM format)
        - ``mallet_output/{lang}/doc-topics.txt``  →  ``mallet_output/doc-topics.txt``
          (converted from dense tab-delimited to sparse "doc_id topic_id weight …" pairs,
          matching PolylingualTM format)
        """
        self._logger.info("-- Creating PolylingualTM-compatible output files …")

        for lang in self._langs:
            lang_folder = self._mallet_out_folder / lang

            # --- thetas ---
            src_thetas = lang_folder / "thetas.npz"
            dst_thetas = self._mallet_out_folder / f"thetas_{lang}.npz"
            if src_thetas.exists():
                _shutil.copy2(str(src_thetas), str(dst_thetas))
                self._logger.info(f"  thetas: {dst_thetas}")

            # --- keys ---
            src_keys = lang_folder / "topickeys.txt"
            dst_keys = self._mallet_out_folder / f"keys_{lang}.txt"
            if src_keys.exists():
                with src_keys.open("r", encoding="utf8") as fin, \
                     dst_keys.open("w", encoding="utf8") as fout:
                    for line in fin:
                        # Mallet LDA topickeys.txt format:
                        #   topic_id\talpha\tword1 word2 word3 …
                        parts = line.strip().split("\t")
                        if len(parts) >= 3:
                            fout.write(parts[2].strip() + "\n")
                        elif len(parts) == 2:
                            # alpha omitted – whole rest is words
                            fout.write(parts[1].strip() + "\n")
                        else:
                            fout.write(line.strip() + "\n")
                self._logger.info(f"  keys:   {dst_keys}")

            # --- doc-topics (dense → sparse) ---
            # PolylingualTM format:
            #   #doc … (header line)
            #   doc_id topic_id weight topic_id weight …
            # LDATM dense format (tab-delimited):
            #   doc_index \t source \t p0 \t p1 \t p2 …
            src_dt = lang_folder / "doc-topics.txt"
            dst_dt = self._mallet_out_folder / "doc-topics.txt"
            if src_dt.exists():
                with src_dt.open("r", encoding="utf8") as fin, \
                     dst_dt.open("w", encoding="utf8") as fout:
                    fout.write("#doc source topic proportion ...\n")
                    for line in fin:
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        cols = stripped.split("\t")
                        if len(cols) < 3:
                            continue
                        doc_id = cols[0]
                        # cols[1] is <source>, cols[2:] are dense topic proportions
                        pairs = []
                        for topic_idx, val in enumerate(cols[2:]):
                            try:
                                weight = float(val)
                            except ValueError:
                                continue
                            if weight > 0:
                                pairs.append(f"{topic_idx} {weight}")
                        fout.write(f"{doc_id} {' '.join(pairs)}\n")
                self._logger.info(f"  doc-topics: {dst_dt}")

        self._logger.info("-- PolylingualTM-compatible outputs created.")

    def _extract_pipe(self):
        """
        Extract a pipe for each language based on its training corpus.
        """
        for lang in self._langs:
            lang_folder = self._mallet_out_folder / lang
            path_corpus = self._mallet_input_folder / f"corpus_{lang}.mallet"
            corpus_txt_path = self._train_data_folder / f"corpus_{lang}.txt"
            path_aux = self._model_folder / f"corpus_aux_{lang}.txt"

            with corpus_txt_path.open('r', encoding='utf8') as f:
                first_line = f.readline()
            with path_aux.open('w', encoding='utf8') as fout:
                fout.write(first_line + '\n')

            path_pipe = lang_folder / "import.pipe"
            cmd = f'{self._mallet_path} import-file --use-pipe-from {path_corpus} --input {path_aux} --output {path_pipe}'

            try:
                self._logger.info(f'-- Extracting pipeline for language {lang}')
                check_output(args=cmd, shell=True)
            except:
                self._logger.error(f'-- Failed to extract pipeline for language {lang}')
            finally:
                path_aux.unlink()

    def infer(
        self,
        docs: List[str],
        lang: str,
        num_iterations: int = 1000,
        doc_topic_thr: float = 0.0,
    ) -> np.ndarray:
        """Perform inference on unseen documents for a specific language."""

        # Folder structure for the language
        lang_folder = self._model_folder / "mallet_output" / lang
        path_pipe = lang_folder / "import.pipe"
        inferencer = lang_folder / "inferencer.mallet"

        # Output folder
        inference_folder = self._model_folder / "inference" / lang
        inference_folder.mkdir(parents=True, exist_ok=True)

        # Write test documents to .txt
        corpus_txt = inference_folder / "corpus.txt"
        with corpus_txt.open("w", encoding="utf8") as fout:
            for i, t in enumerate(docs):
                fout.write(f"{i} 0 {t}\n")

        # Convert to Mallet format
        corpus_mallet_inf = inference_folder / "corpus_inf.mallet"
        doc_topics_file = inference_folder / "doc-topics-inf.txt"
        cmd = f'{self._mallet_path} import-file --use-pipe-from {path_pipe} --input {corpus_txt} --output {corpus_mallet_inf}'
        try:
            self._logger.info(f'-- Running command {cmd}')
            check_output(args=cmd, shell=True)
        except:
            self._logger.error('-- Mallet failed to import data. Revise command')
            return

        # Infer topic proportions
        cmd = f'{self._mallet_path} infer-topics --inferencer {inferencer} --input {corpus_mallet_inf} ' \
            f'--output-doc-topics {doc_topics_file} --doc-topics-threshold {doc_topic_thr} --num-iterations {num_iterations}'
        try:
            self._logger.info(f'-- Running command {cmd}')
            check_output(args=cmd, shell=True)
        except:
            self._logger.error('-- Mallet inference failed. Revise command')
            return

        # Parse results
        cols = [k for k in np.arange(2, self._num_topics + 2)]
        thetas32 = np.loadtxt(doc_topics_file, delimiter='\t',
                            dtype=np.float32, usecols=cols)
        self._logger.info(f"-- -- Inferred thetas shape {thetas32.shape}")

        return thetas32

    
    def _get_more_info(
        self,
        modelFolder: pathlib.Path
    ):

        # Load thetas matrix
        thetas_file = modelFolder.joinpath('doc-topics.txt')
        cols = [k for k in np.arange(2, self._num_topics + 2)]

        # Sparsification of thetas matrix
        self._logger.info('-- -- Sparsifying doc-topics matrix')
        thetas32 = np.loadtxt(thetas_file, delimiter='\t',
                              dtype=np.float32, usecols=cols)
        # Set to zeros all thetas below threshold, and renormalize
        thetas32[thetas32 < self._thetas_thr] = 0
        thetas32 = normalize(thetas32, axis=1, norm='l1')
        print(thetas32.shape)
        thetas = sparse.csr_matrix(thetas32, copy=True)

        # Recalculate topic weights to avoid errors due to sparsification
        alphas = np.asarray(np.mean(thetas32, axis=0)).ravel()

        # Create vocabulary files and calculate beta matrix
        # A vocabulary is available with words provided by the Count Vectorizer object, but the new files need the order used by mallet
        wtcFile = modelFolder.joinpath('word-topic-counts.txt')
        vocab_size = file_lines(wtcFile)
        betas = np.zeros((self._num_topics, vocab_size))
        vocab = []
        term_freq = np.zeros((vocab_size,))

        with wtcFile.open('r', encoding='utf8') as fin:
            for i, line in enumerate(fin):
                elements = line.split()
                vocab.append(elements[1])
                for counts in elements[2:]:
                    tpc = int(counts.split(':')[0])
                    cnt = int(counts.split(':')[1])
                    betas[tpc, i] += cnt
                    term_freq[i] += cnt
        betas = normalize(betas, axis=1, norm='l1')
        
        # Save vocabulary and frequencies
        vocabfreq_file = modelFolder.joinpath('vocab_freq.txt')
        with vocabfreq_file.open('w', encoding='utf8') as fout:
            [fout.write(el[0] + '\t' + str(int(el[1])) + '\n')
             for el in zip(vocab, term_freq)]
        self._logger.info('-- -- Mallet training: Vocabulary file generated')
        
        # Save thetas, alphas, and betas
        np.save(modelFolder.joinpath('alphas.npy'), alphas)
        np.save(modelFolder.joinpath('betas.npy'), betas)
        sparse.save_npz(modelFolder.joinpath('thetas.npz'), thetas)
        
        # Generate also pyLDAvisualization
        # pyLDAvis currently raises some Deprecation warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            import pyLDAvis

        # We will compute the visualization using ndocs random documents
        # In case the model has gone through topic deletion, we may have rows
        # in the thetas matrix that sum up to zero (active topics have been
        # removed for these problematic documents). We need to take this into
        # account
        ndocs = 10000
        validDocs = np.sum(thetas.toarray(), axis=1) > 0
        nValidDocs = np.sum(validDocs)
        if ndocs > nValidDocs:
            ndocs = nValidDocs
        perm = np.sort(np.random.permutation(nValidDocs)[:ndocs])
        # We consider all documents are equally important
        doc_len = ndocs * [1]
        vocabfreq = np.round(ndocs*(alphas.dot(betas))).astype(int)
        vis_data = pyLDAvis.prepare(
            betas,
            thetas[validDocs, ][perm, ].toarray(),
            doc_len,
            vocab,
            vocabfreq,
            lambda_step=0.05,
            sort_topics=False,
            n_jobs=-1)
        with modelFolder.joinpath("pyLDAvis.html").open("w") as f:
            pyLDAvis.save_html(vis_data, f)