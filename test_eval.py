import sys
sys.path.append("/Users/ahmed/Desktop/domain value analyzer/domain-value-analyzer version 4")

from analyzer.pipeline import process_domain

domains = [
    "AutoRentalUs.com",
    "BikesShops.com",
    "AiAgentCompute.com",
    "AppGameHub.com",
    "ActionArchitect.com",
    "BlueOceanCruise.com",
    "AaasToRageContainer.com",
    "AiBusinessBuilderPro.com",
    "BlueDiamondPoolService.com"
]

for d in domains:
    result = process_domain(d.lower())
    print(f"\n--- {d} ---")
    print(f"Verdict: {result.get('Verdict', result.get('DecisionVerdict', 'N/A'))}")
    print(f"Total Score: {result.get('TotalScore', 0)}")
    print(f"Opp Score: {result.get('OpportunityScore', 0)}")
    print(f"Type: {result.get('DomainType', 'N/A')}")
    print(f"Coherence: {result.get('CoherenceScore', 'N/A')} (passes={result.get('CoherencePasses', 'N/A')})")
    if result.get('RejectionReasons'):
        print(f"Rejections: {result['RejectionReasons']}")
    print(f"Price: ${result.get('PriceLow', 0):,}–${result.get('PriceHigh', 0):,}")
