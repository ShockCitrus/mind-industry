
from typing import Dict, Optional, Tuple, List
import subprocess
import re
from pathlib import Path
import pandas as pd
import argparse
import time
from tqdm import tqdm
from transformers import pipeline, AutoTokenizer
from datasets import Dataset

from mind.utils.utils import init_logger, get_optimization_settings


class Translator:
    def __init__(
        self,
        config_path: Path = Path("config/config.yaml"),
        logger=None
    ):
        self._logger = logger if logger else init_logger(config_path, __name__)
        self._opt_settings = get_optimization_settings(str(config_path), self._logger)
        self.models = {}
        self.tokenizers = {}
        self.supported = {
            ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
            ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
            ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
            ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
            ("en", "it"): "Helsinki-NLP/opus-mt-en-it",
            ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
        }
        self.translated_df = None

    def _add_pair(self, src, tgt, repo):
        self.models[(src, tgt)] = pipeline("translation", model=repo)
        self.tokenizers[(src, tgt)] = AutoTokenizer.from_pretrained(repo)

    def _split(
        self,
        df: pd.DataFrame,
        src_lang: str,
        tgt_lang: str,
        text_col: str = "text",
        lang_col: str = "lang"
    ) -> pd.DataFrame:
        """
        Vectorized sentence splitting with token length filtering.
        
        Parameters
        ----------
        df : pd.DataFrame
            Input DataFrame with text to split.
        src_lang : str
            Source language code.
        tgt_lang : str
            Target language code.
        text_col : str
            Column containing text to split.
        lang_col : str
            Column containing language labels.
        
        Returns
        -------
        pd.DataFrame
            DataFrame with one row per sentence.
        """
        import time
        start = time.time()
        
        # Get tokenizer and max length
        tok = self.tokenizers.get((src_lang, tgt_lang))
        if tok is None:
            raise ValueError(f"No tokenizer for {src_lang}->{tgt_lang}")
        
        model_max = getattr(tok, "model_max_length", 512)
        max_tokens = int(model_max * 0.9)  # Leave margin
        
        # Store original columns
        orig_cols = list(df.columns)
        df = df.copy()
        
        # Preserve original ID for tracking
        id_col = "id_preproc" if "id_preproc" in df.columns else df.index.name or "index"
        df["_orig_id"] = df.get(id_col, df.index.astype(str)).astype(str)
        
        # VECTORIZED: Split text into sentences
        # Using regex to handle ". " and ".\n" patterns
        df["_sentences"] = df[text_col].astype(str).str.split(r'(?<=[.!?])\s+', regex=True)
        
        # VECTORIZED: Explode to one row per sentence
        df = df.explode("_sentences", ignore_index=True)
        
        # Filter empty sentences
        df = df[
            (df["_sentences"].notna()) & 
            (df["_sentences"].str.strip() != "")
        ].copy()
        
        if df.empty:
            self._logger.warning("No sentences after splitting")
            return df
        
        # Calculate token lengths in batch (this is the expensive part)
        self._logger.info(f"Calculating token lengths for {len(df)} sentences...")
        sentences = df["_sentences"].tolist()
        
        # Batch tokenization for efficiency
        batch_size = 1000
        token_lengths = []
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i + batch_size]
            lengths = [len(tok.encode(s, truncation=False)) for s in batch]
            token_lengths.extend(lengths)
        
        df["_token_len"] = token_lengths
        
        # Filter by token length
        original_count = len(df)
        df = df[df["_token_len"] < max_tokens].copy()
        filtered_count = original_count - len(df)
        
        if filtered_count > 0:
            self._logger.info(f"Filtered {filtered_count} sentences exceeding {max_tokens} tokens")
        
        # Track dropped document IDs
        if df.empty:
            return df
        
        # Generate new id_preproc with sentence index
        df["_sent_idx"] = df.groupby("_orig_id").cumcount()
        df["id_preproc"] = df["_orig_id"] + "_" + df["_sent_idx"].astype(str)
        
        # Update text column with sentence
        df[text_col] = df["_sentences"]
        
        # Clean up temporary columns
        df = df.drop(columns=["_sentences", "_orig_id", "_token_len", "_sent_idx"])
        df["index"] = range(len(df))
        
        elapsed = time.time() - start
        self._logger.info(
            f"Vectorized sentence split: {len(df)} sentences in {elapsed:.2f}s "
            f"({len(df)/elapsed:.1f} sent/sec)"
        )
        
        return df

    def _translate_split(
        self,
        split_df: pd.DataFrame,
        src_lang: str,
        tgt_lang: str,
        text_col: str = "text"
    ) -> pd.Series:
        """
        Splits the DataFrame into smaller chunks for translation. The pandas Df is converted into a Huggingface Dataset for batch processing.

        Parameters
        ----------
        split_df: pd.DataFrame
            DataFrame containing the sentences to translate.
        src_lang: str
            Source language code.
        tgt_lang: str
            Target language code.
        text_col: str
            Name of the text column to translate.

        Returns
        -------
        pd.Series
            Series containing the translated text.
        """
        ds = Dataset.from_pandas(split_df)
        model = self.models[(src_lang, tgt_lang)]

        def translate_batch(batch):
            out = model(batch[text_col])
            batch["translated_text"] = [o["translation_text"] for o in out]
            return batch

        ds = ds.map(translate_batch, batched=True)
        return ds.to_pandas()["translated_text"]

    def _assemble(
        self,
        split_df: pd.DataFrame,
        translated_text: pd.Series,
        tgt_lang: str,
        text_col: str = "text",
        lang_col: str = "lang"
    ) -> pd.DataFrame:
        """
        Given a DataFrame of split sentences and their translations, reconstructs full translated paragraphs and preserves all original metadata.

        Steps:
        1. Replaces the sentence text in the DataFrame with the translated sentences.
        2. Groups sentences by their original paragraph (using 'id_preproc'), and joins them to form full translated paragraphs.
        3. For each paragraph, restores all metadata columns from the original data (except for the text and id_preproc, which are updated).
        4. Sets the language column to the target language and updates the id to indicate translation.

        Returns a DataFrame where each row is a translated paragraph, with all original metadata preserved and updated for the new language.
        """
        tmp = split_df.copy()
        tmp[text_col] = translated_text.values

        tmp["aux_id"] = tmp["id_preproc"].str.rsplit("_", n=1).str[0]
        grouped = (
            tmp.groupby("aux_id")[text_col]
            .agg(lambda x: ' '.join(x.astype(str).str.strip()))
            .reset_index()
            .rename(columns={text_col: "assembled_text"})
        )

        # Merge back all metadata columns except text_col and id_preproc
        meta_cols = [col for col in tmp.columns if col not in [
            text_col, "id_preproc", "aux_id"]]
        meta_df = tmp.drop_duplicates(subset=["aux_id"])[
            ["aux_id"] + meta_cols]
        merged = (
            meta_df.merge(grouped, on="aux_id", how="outer")
            .rename(columns={"aux_id": "id_preproc", "assembled_text": text_col})
            .assign(id_preproc=lambda x: "T_" + x["id_preproc"])
            .assign(**{lang_col: tgt_lang})
            .reset_index(drop=True)
        )
        return merged

    def translate(
        self,
        path_df: Path,
        src_lang: str,
        tgt_lang: str,
        text_col: str = "text",
        lang_col: str = "lang",
        save_path: str = None
    ):
        """
        Translates the given DataFrame from src_lang to tgt_lang and appends the translated documents. Saves the result to disk if save_path is provided.

        Parameters
        ----------
        path_df: Path
            Path to the input DataFrame (parquet format).
        text_col: str
            name of the text column to translate
        lang_col: str
            name of the language column
        save_path: str
            directory to save the translated DataFrame (as parquet)
        """
        if src_lang == tgt_lang:
            raise ValueError(
                f"Source and target languages must differ. Got: {src_lang}")
        if (src_lang, tgt_lang) not in self.supported:
            raise Exception(
                f"Unsupported language pair: {(src_lang, tgt_lang)}")

        self._logger.info(f"Loading dataframe from {path_df}")
        df = pd.read_parquet(path_df)
        self._logger.info(f"Loaded dataframe with {len(df)} rows.")
        df[lang_col] = df[lang_col].astype(str).str.lower()
        if src_lang.lower() not in df[lang_col].unique():
            raise ValueError(
                f"Source language '{src_lang}' not found in column '{lang_col}'")

        self._logger.info(
            f"Preparing translation pipeline for {src_lang} → {tgt_lang}")
        if (src_lang, tgt_lang) not in self.models:
            repo = self.supported[(src_lang, tgt_lang)]
            self._add_pair(src_lang, tgt_lang, repo)

        self._logger.info(
            f"Splitting paragraphs into sentences for translation...")
        start_time = time.time()
        split_df = self._split(df, src_lang, tgt_lang,
                               text_col=text_col, lang_col=lang_col)
        self._logger.info(
            f"Split into {len(split_df)} sentences. Translating...")
        trans_text = self._translate_split(
            split_df, src_lang, tgt_lang, text_col=text_col)
        self._logger.info(f"Translation complete. Reassembling paragraphs...")
        merged = self._assemble(
            split_df, trans_text, tgt_lang, text_col=text_col, lang_col=lang_col)
        elapsed = time.time() - start_time
        self._logger.info(
            f"Translation and assembly took {elapsed:.2f} seconds.")

        # Append translated docs to original
        self.translated_df = pd.concat([df, merged], ignore_index=True)

        if save_path is not None:
            compression = self._opt_settings.get("parquet_compression", "gzip")
            self.translated_df.to_parquet(save_path, compression=compression)
            self._logger.info(f"Saved translated DataFrame to {save_path} (compression: {compression})")

        return self.translated_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translate a DataFrame using the Translator class.")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to input parquet file.")
    parser.add_argument("--output", type=str, required=True,
                        help="Path to save translated parquet file.")
    parser.add_argument("--src_lang", type=str, required=True,
                        help="Source language code (e.g. 'en').")
    parser.add_argument("--tgt_lang", type=str, required=True,
                        help="Target language code (e.g. 'es').")
    parser.add_argument("--text_col", type=str, default="text",
                        help="Name of the text column.")
    parser.add_argument("--lang_col", type=str, default="lang",
                        help="Name of the language column.")
    args = parser.parse_args()

    translator = Translator()
    translated_df = translator.translate(
        path_df=args.input,
        src_lang=args.src_lang,
        tgt_lang=args.tgt_lang,
        text_col=args.text_col,
        lang_col=args.lang_col,
        save_path=args.output
    )
    print(
        f"Translation complete. Saved to {args.output}. Rows: {len(translated_df)}")
