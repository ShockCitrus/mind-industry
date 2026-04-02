#!/usr/bin/env python3
"""
Inspect and validate the expanded 150-row dataset.
Shows contradiction pairs, category distribution, and sample queries.
"""

import pandas as pd
import sys
from pathlib import Path

def inspect_dataset(parquet_path: str = "data/expanded/documents_150.parquet"):
    """Inspect dataset structure and contradictions."""

    df = pd.read_parquet(parquet_path)

    print(f"Dataset: {parquet_path}")
    print(f"Total rows: {len(df)}")
    print(f"Shape: {df.shape}\n")

    # Language balance
    print("Language Distribution:")
    print(f"  EN: {(df['lang'] == 'EN').sum()}")
    print(f"  ES: {(df['lang'] == 'ES').sum()}\n")

    # Contradiction balance
    print("Contradiction Distribution:")
    print(f"  Contradictory pairs: {df['is_contradictory'].sum() // 2}")
    print(f"  Non-contradictory pairs: {(~df['is_contradictory']).sum() // 2}\n")

    # Category distribution
    print("Category Distribution:")
    for cat in sorted(df['category'].unique()):
        count = (df['category'] == cat).sum()
        pairs = count // 2
        is_contra = (df[df['category'] == cat]['is_contradictory']).sum() // 2
        print(f"  {cat:15} {count:3} passages ({pairs:2} pairs, {is_contra:2} contradictory)")

    # Find EN-ES pairs
    print("\n" + "="*80)
    print("Sample Contradiction Pairs (EN ↔ ES):")
    print("="*80)

    for title in df['title'].unique()[:5]:
        subset = df[df['title'] == title]
        en_rows = subset[subset['lang'] == 'EN']
        es_rows = subset[subset['lang'] == 'ES']

        if len(en_rows) > 0 and len(es_rows) > 0:
            en = en_rows.iloc[0]
            es = es_rows.iloc[0]

            print(f"\nTitle: {en['title']}")
            print(f"Category: {en['category']} | Contradictory: {en['is_contradictory']}")
            print(f"\n  EN: {en['text'][:100]}...")
            print(f"  ES: {es['text'][:100]}...")

    # Statistics
    print("\n" + "="*80)
    print("Statistics:")
    print("="*80)

    avg_text_len = df['text'].str.len().mean()
    min_text_len = df['text'].str.len().min()
    max_text_len = df['text'].str.len().max()

    print(f"Text length (characters):")
    print(f"  Min: {min_text_len}")
    print(f"  Avg: {avg_text_len:.0f}")
    print(f"  Max: {max_text_len}")

    # Data completeness
    print(f"\nData Completeness:")
    print(f"  Missing values: {df.isnull().sum().sum()}")
    print(f"  Unique titles: {df['title'].nunique()}")
    print(f"  Unique IDs: {df['id_preproc'].nunique()}")

    # Validation
    print("\n" + "="*80)
    print("Validation:")
    print("="*80)

    # Check for balanced EN/ES per title
    title_lang_count = df.groupby('title')['lang'].value_counts().unstack(fill_value=0)
    unbalanced = (title_lang_count['EN'] != title_lang_count['ES']).sum()

    if unbalanced == 0:
        print("✓ All titles have balanced EN-ES pairs")
    else:
        print(f"✗ {unbalanced} titles have unbalanced EN-ES pairs")

    # Check for duplicate IDs
    if df['id_preproc'].nunique() == len(df):
        print("✓ All IDs are unique")
    else:
        print(f"✗ Found {len(df) - df['id_preproc'].nunique()} duplicate IDs")

    # Check contradiction flag consistency
    contra_titles = df[df['is_contradictory']]['title'].unique()
    print(f"✓ Contradictory content covers {len(contra_titles)} unique topics")

    print("\n" + "="*80)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/expanded/documents_150.parquet"
    inspect_dataset(path)
