import sys
import pandas as pd
sys.path.append("/Users/ahmed/Desktop/domain value analyzer/domain-value-analyzer version 4")

from analyzer.pipeline import process_domain

df = pd.read_csv("/Users/ahmed/Downloads/top_domain_sales_sample.csv")
for _, row in df.head(20).iterrows():
    d = row['domain']
    result = process_domain(d.lower())
    print(f"\n--- {d} ---")
    if 'ExcludeReason' in result:
        print(f"EXCLUDED: {result['ExcludeReason']}")
        continue
    print(f"Verdict: {result.get('Verdict', result.get('DecisionVerdict', 'N/A'))}")
    print(f"Total Score: {result.get('TotalScore', 0)}")
    print(f"Type: {result.get('DomainType', 'N/A')}")
    print(f"Reasoning: {result.get('Reasoning', 'N/A')}")
    print(f"Price: ${result.get('PriceLow', 0):,}–${result.get('PriceHigh', 0):,}")
