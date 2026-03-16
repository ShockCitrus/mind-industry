import argparse
from pathlib import Path

import pandas as pd
from mind.utils.utils import init_logger, get_optimization_settings
from tqdm import tqdm


class Segmenter():
    def __init__(
        self,
        config_path: Path = Path("config/config.yaml"),
        logger=None
    ):
        self._logger = logger if logger else init_logger(config_path, __name__)
        self._opt_settings = get_optimization_settings(str(config_path), self._logger)

    def segment(
        self,
        path_df: Path,
        path_save: Path,
        text_col: str = "text",
        id_col: str = "id_preproc",
        min_length: int = 100,
        sep: str = "\n"
    ):
        """
        Segments each entry in the specified text column into paragraphs using
        vectorized pandas operations for maximum performance.

        Parameters:
        -----------
        path_df : Path
            Path to input Parquet file.
        path_save : Path
            Path to save segmented output.
        text_col : str 
            Name of the column to segment.
        id_col : str
            Name of the ID column to use for generating paragraph IDs.
        min_length : int
            Minimum length for a paragraph to be kept.
        sep : str
            Separator for splitting paragraphs (default: newline).
        """
        import time

        self._logger.info(f"Loading dataframe from {path_df}")
        df = pd.read_parquet(path_df)
        original_count = len(df)
        self._logger.info(f"Loaded {original_count} rows. Starting vectorized segmentation...")

        start_time = time.time()

        # Preserve original document text and ID before transformation
        df["full_doc"] = df[text_col].astype(str)
        df["_orig_id"] = df[id_col].astype(str)

        # Store original column list (excluding our new columns)
        orig_cols = [c for c in df.columns if c not in ["full_doc", "_orig_id"]]

        # VECTORIZED: Split text into list of paragraphs
        df["_paragraphs"] = df[text_col].str.split(sep)

        # VECTORIZED: Explode to one row per paragraph
        df = df.explode("_paragraphs", ignore_index=True)

        # VECTORIZED: Filter empty/short paragraphs
        df = df[
            (df["_paragraphs"].notna()) & 
            (df["_paragraphs"].str.strip() != "") &
            (df["_paragraphs"].str.len() > min_length)
        ].copy()

        # Replace text column with paragraph content
        df[text_col] = df["_paragraphs"]

        # Generate sequential paragraph index per original document
        df["_para_idx"] = df.groupby("_orig_id").cumcount().astype(str)
        df["id_preproc"] = df["_orig_id"] + "_" + df["_para_idx"]

        # Clean up temporary columns
        df = df.drop(columns=["_paragraphs", "_orig_id", "_para_idx"])

        # Reset global ID
        df["id"] = range(len(df))

        elapsed = time.time() - start_time
        self._logger.info(
            f"Vectorized segmentation took {elapsed:.2f}s "
            f"({original_count/elapsed:.1f} docs/sec)"
        )
        self._logger.info(f"Segmented into {len(df)} paragraphs. Saving to {path_save}")

        # Use optimized compression from config
        compression = self._opt_settings.get("parquet_compression", "zstd")
        df.to_parquet(path_save, compression=compression)
        self._logger.info(f"Saved segmented dataframe to {path_save} (compression: {compression})")

        return path_save


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Segmenter to split documents into segments.")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to input file (parquet or csv).")
    parser.add_argument("--output", type=str, required=True,
                        help="Path to save segmented output file.")
    parser.add_argument("--text_col", type=str, default="text",
                        help="Name of the text column to segment.")
    parser.add_argument("--min_length", type=int, default=100,
                        help="Minimum length for a paragraph to be kept.")
    parser.add_argument("--separator", type=str, default="\n",
                        help="Separator for splitting paragraphs.")
    args = parser.parse_args()

    segmenter = Segmenter()
    result_path = segmenter.segment(
        path_df=Path(args.input),
        path_save=Path(args.output),
        text_col=args.text_col,
        min_length=args.min_length,
        sep=args.separator
    )
    
    # Read the result to get row count
    result_df = pd.read_parquet(result_path)
    print(
        f"Segmentation complete. Saved to {args.output}. Rows: {len(result_df)}")
