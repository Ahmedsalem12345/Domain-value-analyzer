"""
Performance Benchmark — Domain Value Analyzer V4.

Measures:
  - KPS scoring speed (extract_keywords + score_kps)
  - Full pipeline speed (process_domain)
  - Domains/sec throughput

Run: python -m tests.benchmark_performance
"""
import sys
import time
import statistics
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Sample domains for benchmarking (diverse types)
BENCHMARK_DOMAINS = [
    "parallelai.com", "casino.com", "insurance.com", "taxi.com",
    "miamiplumbing.com", "dentistchicago.com", "realtorminnesota.com",
    "healthcareillinois.com", "airealestate.com", "bestinsurance.com",
    "myshop4less.com", "omdurmaninsurance.com", "xzqwplm.com",
    "openaihelp.com", "devcell.com", "zentrova.com", "cloudhosting.com",
    "bitcoinexchange.com", "newyorkdentist.com", "dubairealestate.com",
    "fastcars.com", "greenenergy.io", "smartfinance.com", "datascience.ai",
    "homecleaning.com", "petcare.net", "fitnessclub.com", "travelguide.com",
    "jobsearch.com", "fooddelivery.com", "musicstudio.com", "photoeditor.com",
    "legaladvice.com", "creditrepair.com", "autoloan.com", "cybersecurity.io",
    "machinelearning.ai", "cloudcomputing.com", "webdesign.co", "seoagency.com",
    # More complex patterns
    "bestlawyermiami.com", "cheapinsuranceonline.com", "topdentalcare.com",
    "realestateinvesting.com", "personalfinancetips.com", "healthyrecipes.com",
    "onlinepharmacy.com", "luxuryhotels.com", "sportsbetting.com",
    "digitalmarketing.com",
]


def benchmark_kps(n_domains=100):
    """Benchmark KPS scoring speed."""
    from analyzer.retail_kps import score_kps, _load
    
    # Ensure data is loaded (don't count load time)
    _load()
    
    domains = (BENCHMARK_DOMAINS * ((n_domains // len(BENCHMARK_DOMAINS)) + 1))[:n_domains]
    
    times = []
    for domain in domains:
        name = domain.split('.')[0]
        start = time.perf_counter()
        score_kps(name)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    return {
        "total_ms": sum(times) * 1000,
        "avg_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "p95_ms": sorted(times)[int(len(times) * 0.95)] * 1000,
        "domains": n_domains,
    }


def benchmark_pipeline(n_domains=100):
    """Benchmark full pipeline speed."""
    from analyzer.pipeline import process_domain
    
    domains = (BENCHMARK_DOMAINS * ((n_domains // len(BENCHMARK_DOMAINS)) + 1))[:n_domains]
    
    times = []
    for domain in domains:
        start = time.perf_counter()
        process_domain(domain)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    total = sum(times)
    return {
        "total_sec": total,
        "avg_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "p95_ms": sorted(times)[int(len(times) * 0.95)] * 1000,
        "domains_per_sec": n_domains / total if total > 0 else 0,
        "domains": n_domains,
    }


def benchmark_domain_results():
    """Benchmark specific domains and capture their scores for before/after comparison."""
    from analyzer.pipeline import process_domain
    
    test_domains = [
        "parallelai.com", "casino.com", "insurance.com", "taxi.com",
        "miamiplumbing.com", "dentistchicago.com", "realtorminnesota.com",
        "healthcareillinois.com", "airealestate.com", "bestinsurance.com",
        "myshop4less.com", "omdurmaninsurance.com", "xzqwplm.com",
        "openaihelp.com",
    ]
    
    results = []
    for domain in test_domains:
        start = time.perf_counter()
        r = process_domain(domain)
        elapsed = time.perf_counter() - start
        
        results.append({
            "domain": domain,
            "verdict": r.get("Verdict", "EXCLUDED"),
            "total_score": r.get("TotalScore", 0),
            "domain_type": r.get("DomainType", ""),
            "opportunity_score": r.get("OpportunityScore", "N/A"),
            "risk_flags": r.get("RiskFlags", []),
            "sell_through": r.get("SellThroughProbability", "N/A"),
            "max_buy_price": r.get("MaxAcquisitionPrice", "N/A"),
            "decision_verdict": r.get("DecisionVerdict", "N/A"),
            "decision_reason": r.get("DecisionReason", "N/A"),
            "price_low": r.get("PriceLow", 0),
            "price_high": r.get("PriceHigh", 0),
            "time_ms": elapsed * 1000,
        })
    
    return results


def main():
    print("=" * 70)
    print("  DOMAIN VALUE ANALYZER V4 — PERFORMANCE BENCHMARK")
    print("=" * 70)
    
    # --- KPS Benchmark ---
    print("\n📊 KPS Scoring Benchmark (100 domains)...")
    kps = benchmark_kps(100)
    print(f"   Total:  {kps['total_ms']:.1f} ms")
    print(f"   Avg:    {kps['avg_ms']:.2f} ms/domain")
    print(f"   Median: {kps['median_ms']:.2f} ms/domain")
    print(f"   P95:    {kps['p95_ms']:.2f} ms/domain")
    
    # --- Pipeline Benchmark ---
    for n in [100, 500]:
        print(f"\n📊 Full Pipeline Benchmark ({n} domains)...")
        pipe = benchmark_pipeline(n)
        print(f"   Total:  {pipe['total_sec']:.2f} sec")
        print(f"   Avg:    {pipe['avg_ms']:.2f} ms/domain")
        print(f"   Median: {pipe['median_ms']:.2f} ms/domain")
        print(f"   P95:    {pipe['p95_ms']:.2f} ms/domain")
        print(f"   Speed:  {pipe['domains_per_sec']:.1f} domains/sec")
    
    # --- Domain Results ---
    print("\n📊 Domain Results Benchmark...")
    results = benchmark_domain_results()
    print(f"\n{'Domain':<30} {'Verdict':<8} {'Score':>5} {'Type':<16} {'Price':>12} {'ms':>7}")
    print("-" * 85)
    for r in results:
        price = f"${r['price_low']:,}-${r['price_high']:,}" if r['price_low'] > 0 else "N/A"
        print(f"{r['domain']:<30} {r['verdict']:<8} {r['total_score']:>5} {r['domain_type']:<16} {price:>12} {r['time_ms']:>6.1f}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
