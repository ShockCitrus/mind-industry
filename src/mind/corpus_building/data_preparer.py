"""
Builds a polylingual dataset for the PLTM wrapper, starting from two input parquet files:
    - One file per language: anchor and comparison.
    - Each row represents a chunk/passage with its original metadata.
    - 'lemmas' contains the lemmatized text from NLPipe (run once per language).
    - 'lemmas_tr' contains lemmas from the cross-language translation (from the other language's NLPipe output).

Assumptions:
    - Two input parquet files, one for the anchor language and one for the comparison language.
    - Chunk IDs follow patterns like:
        Originals:     EN_<doc>_<chunk>   /  DE_<doc>_<chunk> / ES_...
        Translations:  T_EN_<doc>_<chunk> / T_DE_<doc>_<chunk> ...

Output columns (plus any extra metadata preserved):
    - chunk_id   (from schema)
    - doc_id     (from schema)
    - full_doc   (from summary-like field if available)
    - text       (original chunk text)
    - lang       (UPPER, e.g., EN/DE/ES)
    - lemmas     (from NLPipe run on this language)
    - lemmas_tr  (from the other language's NLPipe run over translations)
    - title, url, equivalence (if present)
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from mind.utils.utils import init_logger, get_optimization_settings


class DataPreparer:
    def __init__(
        self,
        preproc_script: Optional[str] = None,
        config_path: Optional[str] = None,
        stw_path: Optional[str] = None,
        python_exe: str = "python3",
        spacy_models: Optional[Dict[str, str]] = None,
        schema: Optional[Dict[str, str]] = None,
        config_logger_path: Path = Path("config/config.yaml"),
        logger=None
    ):
        self._logger = logger if logger else init_logger(
            config_logger_path, __name__)
        self._opt_settings = get_optimization_settings(str(config_logger_path), self._logger)

        # configure NLPipe
        self.preproc_script = Path(preproc_script) if preproc_script else None
        self.config_path = Path(config_path) if config_path else None
        self.stw_path = Path(stw_path) if stw_path else None
        self.python_exe = python_exe
        self.spacy_models = {k.upper(): v for k, v in (
            spacy_models or {}).items()}

        # Schema mapping: user must provide all required fields; optional fields are preserved automatically
        required_fields = ['chunk_id', 'text', 'lang', 'full_doc', 'doc_id']
        msg_fails = (
            "You must provide a schema mapping all required fields ('chunk_id', 'text', 'lang', 'full_doc', 'doc_id') to column names:\n"
            "- 'chunk_id': unique id for each chunk/passage\n"
            "- 'text': text content of the chunk\n"
            "- 'lang': language code (e.g., EN, ES)\n"
            "- 'full_doc': full document before chunking\n"
            "- 'doc_id': document id for each chunk\n"
            "Any other columns in your input file will be preserved as extra metadata.\n\n"
            "Example: schema = {\n"
            "    'chunk_id': 'id_preproc',\n"
            "    'text': 'chunk_text',\n"
            "    'lang': 'language',\n"
            "    'full_doc': 'summary',\n"
            "    'doc_id': 'id'\n"
            "}\n"
        )
        if schema is None or not all(f in schema for f in required_fields):
            raise ValueError(msg_fails)
        self.schema = schema

    @staticmethod
    def _upper_lang(x) -> str:
        return (x if isinstance(x, str) else str(x)).strip().upper()

    def _starts_with(self, series: pd.Series, prefix: str) -> pd.Series:
        return series.fillna("").astype(str).str.startswith(prefix)

    def _normalize(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Rename required columns according to schema and preserve any other metadata that was in the original dataframe.
        """
        df = df.copy()

        # Required fields
        c_chunk = self.schema.get("chunk_id")
        c_text = self.schema.get("text")
        c_lang = self.schema.get("lang")
        c_full = self.schema.get("full_doc")
        c_doc = self.schema.get("doc_id")

        if not c_chunk or not c_text or not c_lang or not c_full:
            raise ValueError(
                "Schema must provide 'chunk_id', 'text', 'lang', and 'full_doc' column names.")
        for col in [c_chunk, c_text, c_lang, c_full]:
            if col not in df.columns:
                raise ValueError(
                    f"Column '{col}' specified in schema is missing from DataFrame.")

        # Build normalized frame
        out = pd.DataFrame({
            "chunk_id": df[c_chunk].astype(str),
            "text": df[c_text],
            "full_doc": df[c_full],
            "doc_id": df[c_doc].astype(str),
        })

        # lang
        lang_val = df[c_lang].iloc[0] if df[c_lang].notna().any() else "XX"
        if lang_val == "XX":
            raise ValueError(
                f"Language column '{c_lang}' has no valid entries. Please check your data."
            )
        out["lang"] = self._upper_lang(lang_val)

        # Keep any extra columns from input that are not mapped by schema
        mapped_cols = set([c_chunk, c_text, c_lang, c_full, c_doc])
        extras = [c for c in df.columns if c not in mapped_cols]
        for c in extras:
            out[c] = df[c]

        return out

    def _spacy_model_for(self, lang_upper: str) -> str:
        """Get the spaCy model name for a specific language."""
        if not self.spacy_models or self._upper_lang(lang_upper) not in self.spacy_models:
            raise ValueError(f"No spaCy model configured for '{lang_upper}'. "
                             f"Provide spacy_models like {{'en':'en_core_web_sm'}}.")
        return self.spacy_models[self._upper_lang(lang_upper)]

    def _preprocess_df(
        self,
        df: pd.DataFrame,
        lang_upper: str,
        tag: str,
        path_save: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        Run NLPipe on a temporary parquet file containing only the required columns:
        - id_preproc (from df['chunk_id'])
        - text (from df['text'])
        - lang (from df['lang'])
        After NLPipe processes the file and adds a 'lemmas' column, merge these lemmas back into the normalized DataFrame using 'chunk_id' as the key.
        """

        # normalized columns must exist
        required = {"chunk_id", "text", "lang"}
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(
                f"_preprocess_df expects normalized df with columns {required}. "
                f"Missing: {missing}. Did _normalize() set 'chunk_id' from your schema?"
            )

        tmp_dir = (Path(path_save).parent / "_tmp_preproc")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # temp parquet for nlpipe
        work = pd.DataFrame({
            "id_preproc": df["chunk_id"].astype(str),
            "text":  df["text"],
            "lang": df["lang"].astype(str).str.lower(),
        })
        tmp_parq = tmp_dir / f"{tag}_{lang_upper}.parquet"
        compression = self._opt_settings.get("parquet_compression", "gzip")
        work.to_parquet(tmp_parq, compression=compression)

        # run NLPipe
        if self.preproc_script and self.config_path and self.stw_path:
            cmd = [
                self.python_exe, str(self.preproc_script),
                "--source_path", str(tmp_parq),
                "--source_type", "parquet",
                "--source", "mind",
                "--destination_path", str(tmp_parq),
                "--lang", lang_upper.lower(),
                "--spacy_model", self._spacy_model_for(lang_upper),
                "--config_file", str(self.config_path),
                "--stw_path", str(self.stw_path),
            ]
            print("Running NLPipe:", " ".join(cmd))
            # Ensure subprocess inherits PYTHONPATH with NLPipe source dir
            import os as _os
            env = _os.environ.copy()
            nlpipe_src = str(Path(self.preproc_script).parent.parent)
            existing = env.get("PYTHONPATH", "")
            if nlpipe_src not in existing:
                env["PYTHONPATH"] = f"{nlpipe_src}:{existing}" if existing else nlpipe_src
            subprocess.run(cmd, check=True, env=env)
            print(f"✓ Preprocessed (lang={lang_upper})")
        else:
            print("Preprocessing skipped (not configured).")
            return df

        # read back NLPipe output and merge lemmas back by id_preproc - chunk_id
        proc = pd.read_parquet(tmp_parq)
        if "id_preproc" not in proc.columns or "lemmas" not in proc.columns:
            raise RuntimeError(
                f"NLPipe output missing id_preproc/lemmas; got: {list(proc.columns)}")

        merged = df.merge(
            proc[["id_preproc", "lemmas"]],
            left_on="chunk_id",
            right_on="id_preproc",
            how="left",
            validate="one_to_one",
        )

        to_drop = [c for c in merged.columns if c.startswith("id_preproc")]
        merged = merged.drop(columns=to_drop)

        # remove tmp file
        tmp_parq.unlink(missing_ok=True)

        return merged

    @staticmethod
    def _pair_key_from_chunk_id(chunk_id: str, row_lang: str) -> Tuple[str, str]:
        """
        Returns a stable key representing the *original source* chunk, regardless
        of whether the row is original or translated.

        Examples:
          EN_12_3     + row_lang=EN  -> ("EN", "12_3")
          T_EN_12_3   + row_lang=DE  -> ("EN", "12_3")
          DE_77_0     + row_lang=DE  -> ("DE", "77_0")
          T_DE_77_0   + row_lang=EN  -> ("DE", "77_0")
        """
        s = str(chunk_id)
        m = re.match(r"^T_([A-Za-z]{2})_(.+)$", s)
        if m:
            return (m.group(1).upper(), m.group(2))
        m2 = re.match(r"^([A-Za-z]{2})_(.+)$", s)
        if m2:
            return (m2.group(1).upper(), m2.group(2))
        return (row_lang.upper(), s)

    def format_dataframes(
        self,
        anchor_path: Path,
        comparison_path: Path,
        path_save: Optional[Path] = None
    ) -> None:
        """
        Formats the anchor and target dataframes according to the specified schema, runs NLPipe preprocessing on both languages, and merges the results to produce a unified dataframe with lemmas from both the original and translated texts.
        """

        self._logger.info("Starting format_dataframes process...")

        anchor_df = pd.read_parquet(anchor_path)
        comparison_df = pd.read_parquet(comparison_path)

        # Use lang column directly from schema
        anchor_lang = str(anchor_df[self.schema["lang"]].iloc[0]).upper()
        comp_lang = str(comparison_df[self.schema["lang"]].iloc[0]).upper()
        self._logger.info(
            f"Anchor language: {anchor_lang}, Comparison language: {comp_lang}")

        # No decontamination or stable ordering needed after translation
        anc = anchor_df.copy()
        comp = comparison_df.copy()

        # Normalize columns to a common schema
        self._logger.info("Normalizing columns to a common schema...")
        anc_norm = self._normalize(anc)
        comp_norm = self._normalize(comp)

        # Save per-language temporaries, run NLPipe once per language to fill 'lemmas'
        tmp_dir = (Path(path_save).parent / "_tmp_preproc")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        anc_parq = tmp_dir / f"anchor_{anchor_lang}.parquet"
        comp_parq = tmp_dir / f"comparison_{comp_lang}.parquet"

        compression = self._opt_settings.get("parquet_compression", "gzip")
        anc_norm.to_parquet(anc_parq, compression=compression)
        comp_norm.to_parquet(comp_parq, compression=compression)
        self._logger.info(
            f"Saved anchor and comparison normalized parquets to {tmp_dir}")

        # Run preprocessing per language
        self._logger.info(
            "Running NLPipe preprocessing for anchor and comparison...")
        anc_proc = self._preprocess_df(
            anc_norm, anchor_lang, tag="anchor", path_save=path_save)
        comp_proc = self._preprocess_df(
            comp_norm, comp_lang, tag="comparison", path_save=path_save)

        # Build pairing keys representing the original source chunk
        def add_pair_key(df: pd.DataFrame) -> pd.DataFrame:
            df = df.copy()
            keys: List[Tuple[str, str]] = [
                self._pair_key_from_chunk_id(cid, L)
                for cid, L in zip(df["chunk_id"].astype(str), df["lang"].astype(str))
            ]
            df["pair_src_lang"] = [k[0] for k in keys]
            df["pair_rest"] = [k[1] for k in keys]
            df["pair_key"] = df["pair_src_lang"] + ":" + df["pair_rest"]
            return df

        anc_proc = add_pair_key(anc_proc)
        comp_proc = add_pair_key(comp_proc)

        # For EN rows, lemmas_tr should come from DE's translations of EN originals: rows in comparison with id 'T_EN_...'
        # But thanks to pair_key, we can simply map by pair_key.
        # Build maps from each side's *translation rows* to their lemmas:
        def is_translation_of(lang_src: str, df: pd.DataFrame) -> pd.Series:
            # rows whose chunk_id starts with f"T_{lang_src}_"
            return df["chunk_id"].astype(str).str.startswith(f"T_{lang_src}_")

        anc_trans_map = anc_proc.loc[is_translation_of(comp_lang, anc_proc), [
            "pair_key", "lemmas"]].dropna()
        tgt_trans_map = comp_proc.loc[is_translation_of(anchor_lang, comp_proc), [
            "pair_key", "lemmas"]].dropna()

        # translations of COMPARISON in ANCHOR
        map_from_anc = dict(
            zip(anc_trans_map["pair_key"], anc_trans_map["lemmas"]))
        # translations of ANCHOR in COMPARISON
        map_from_tgt = dict(
            zip(tgt_trans_map["pair_key"], tgt_trans_map["lemmas"]))

        # Fill lemmas_tr:
        # - For anchor originals (pair_key = ANCHOR:<rest>), find lemmas in comparison translations (map_from_tgt)
        # - For comparison originals, find lemmas in anchor translations (map_from_anc)
        anc_proc["lemmas_tr"] = anc_proc["pair_key"].map(map_from_tgt)
        comp_proc["lemmas_tr"] = comp_proc["pair_key"].map(map_from_anc)

        # keep only originals (no T_* rows) for the final output
        def is_original(df): return ~df["chunk_id"].astype(
            str).str.startswith("T_")
        anc_orig = anc_proc[is_original(anc_proc)].copy()
        comp_orig = comp_proc[is_original(comp_proc)].copy()

        # drop pairing helper columns
        cols_to_drop = ["pair_src_lang", "pair_rest", "pair_key"]
        for c in cols_to_drop:
            if c in anc_orig.columns:
                anc_orig.drop(columns=c, inplace=True)
            if c in comp_orig.columns:
                comp_orig.drop(columns=c, inplace=True)

        # final stack
        final_df = pd.concat([anc_orig, comp_orig], ignore_index=True)

        # drop all rows where lemmas is None
        final_df = final_df[~final_df.lemmas.isnull()]
        # replace None in lemmas_tr with empty string
        final_df["lemmas_tr"] = final_df["lemmas_tr"].fillna("")

        # no duplicate chunk_ids
        assert not final_df["chunk_id"].duplicated().any(), (
            f"Duplicate chunk_id values found in final dataframe: "
            f"{final_df[final_df['chunk_id'].duplicated(keep=False)]['chunk_id'].tolist()}"
        )
        # all lemmas and lemmas_tr are non-null
        assert not final_df["lemmas"].isnull().any(), (
            f"Null lemmas found in final dataframe for chunk_ids: "
            f"{final_df[final_df['lemmas'].isnull()]['chunk_id'].tolist()}"
        )
        assert not final_df["lemmas_tr"].isnull().any(), (
            f"Null lemmas_tr found in final dataframe for chunk_ids: "
            f"{final_df[final_df['lemmas_tr'].isnull()]['chunk_id'].tolist()}"
        )

        # the number of rows in anchor_lang is equals to that of comparison_lang
        n_anc = len(final_df[final_df["lang"] == anchor_lang])
        n_comp = len(final_df[final_df["lang"] == comp_lang])
        assert n_anc == n_comp, f"Number of rows in anchor ({n_anc}) and comparison ({n_comp}) do not match."

        # Save unified parquet
        if path_save:
            final_df.to_parquet(path_save)
            self._logger.info(f"Saved: {path_save}")

        return final_df

    def format_monolingual(
        self,
        input_path: Path,
        path_save: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        Format a monolingual dataset for use with LDATM topic modeling.

        Unlike :meth:`format_dataframes` (which expects anchor + comparison
        language files), this method takes a single parquet with one language,
        runs NLPipe for lemmatization, and sets ``lemmas_tr`` to empty string
        so the output schema matches the bilingual pipeline.

        Parameters
        ----------
        input_path : Path
            Path to a segmented parquet file containing a single language.
        path_save : Path, optional
            Where to save the resulting parquet.

        Returns
        -------
        pd.DataFrame
            The processed DataFrame with columns matching ``format_dataframes`` output.
        """
        self._logger.info("Starting format_monolingual process ...")

        df = pd.read_parquet(input_path)
        # If schema has a non-empty lang column name, use it; otherwise fall back to 'lang'
        lang_col = self.schema.get("lang", "") or "lang"
        if lang_col not in df.columns:
            lang_col = "lang"
        lang = str(df[lang_col].iloc[0]).upper()
        self._logger.info(f"Detected monolingual dataset in language: {lang}")

        # Normalize columns to common schema
        norm = self._normalize(df)

        # Run NLPipe to generate lemmas
        self._logger.info(f"Running NLPipe for {lang} ...")
        proc = self._preprocess_df(norm, lang, tag="mono", path_save=path_save)

        # No cross-language translations for monolingual data
        proc["lemmas_tr"] = ""

        # Assign doc_id with language prefix (matching bilingual convention)
        proc["doc_id"] = proc["lang"] + "_" + proc["chunk_id"].astype(str)

        # Drop rows where lemmas is None (NLPipe may have failed for some)
        proc = proc[~proc["lemmas"].isnull()]

        # Validate
        assert not proc["chunk_id"].duplicated().any(), (
            f"Duplicate chunk_id values found: "
            f"{proc[proc['chunk_id'].duplicated(keep=False)]['chunk_id'].tolist()}"
        )
        assert not proc["lemmas"].isnull().any(), "Null lemmas found"

        if path_save:
            proc.to_parquet(path_save)
            self._logger.info(f"Saved monolingual dataset: {path_save}")

        return proc

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Run DataPreparer to build a polylingual dataset.")
    parser.add_argument("--anchor", type=str, required=True,
                        help="Path to anchor language parquet file.")
    parser.add_argument("--comparison", type=str, required=True,
                        help="Path to comparison language parquet file.")
    parser.add_argument("--output", type=str, required=True,
                        help="Path to save the output parquet file.")
    parser.add_argument("--schema", type=str, required=True,
                        help="JSON string or path to schema mapping required columns.")
    args = parser.parse_args()

    try:
        if args.schema.endswith('.json'):
            with open(args.schema, 'r') as f:
                schema = json.load(f)
        else:
            schema = json.loads(args.schema)
    except Exception as e:
        raise ValueError(f"Failed to load schema: {e}")

    preparer = DataPreparer(schema=schema)
    final_df = preparer.format_dataframes(
        anchor_path=Path(args.anchor),
        comparison_path=Path(args.comparison),
        path_save=Path(args.output)
    )
    print(
        f"Polylingual dataset created and saved to {args.output}. Rows: {len(final_df)}")
