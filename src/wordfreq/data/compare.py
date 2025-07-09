import json
import heapq
import statistics
import csv
from pathlib import Path
import argparse
from typing import Dict, List, Tuple, Set, Any

def load_frequency_data(file_path: str) -> Dict[str, int]:
    """Load word frequency data from a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['global_word_frequency']

def create_rank_dictionary(frequency_dict: Dict[str, int]) -> Dict[str, int]:
    """Convert frequency dictionary to rank dictionary.
    
    Words are ranked by frequency (highest frequency = rank 1).
    Words with the same frequency get the same rank.
    """
    # Sort words by frequency in descending order
    sorted_items = sorted(frequency_dict.items(), key=lambda x: x[1], reverse=True)
    
    # Create a dictionary mapping words to their ranks
    rank_dict = {}
    current_rank = 1
    prev_freq = None
    
    for i, (word, freq) in enumerate(sorted_items):
        # If this frequency is different from the previous one, update the rank
        if freq != prev_freq:
            current_rank = i + 1
        
        rank_dict[word] = current_rank
        prev_freq = freq
    
    return rank_dict

def harmonic_mean(values: List[float]) -> float:
    """Calculate the harmonic mean of a list of values."""
    return len(values) / sum(1/v for v in values)

def compare_multiple_ranks(rank_dicts: List[Dict[str, int]], file_names: List[str], default_rank: int = 6000) -> List[Tuple[str, List[int], float, float]]:
    """Compare multiple rank dictionaries and find words with significant rank changes.
    
    Args:
        rank_dicts: List of rank dictionaries from different files
        file_names: Names of the files (for reporting)
        default_rank: Rank to assign to words not present in a particular list
        
    Returns:
        List of tuples containing (word, [ranks], harmonic_mean, max_diff)
    """
    # Get the set of all words across all dictionaries
    all_words = set()
    for rank_dict in rank_dicts:
        all_words.update(rank_dict.keys())
    
    # Calculate statistics for each word
    word_stats = []
    for word in all_words:
        # Get ranks across all files, use default_rank if word not in a file
        ranks = [rank_dict.get(word, default_rank) for rank_dict in rank_dicts]
        
        # Calculate harmonic mean of ranks
        harm_mean = harmonic_mean(ranks)
        
        # Calculate maximum rank difference
        max_diff = max(ranks) - min(ranks)
        
        word_stats.append((word, ranks, harm_mean, max_diff))
    
    return word_stats

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Compare word frequency rankings across multiple files')
    parser.add_argument('files', nargs='+', help='JSON files containing word frequency data')
    parser.add_argument('--default-rank', type=int, default=6000, 
                        help='Default rank for words not found in a list (default: 6000)')
    parser.add_argument('--output', default='rank_changes.txt', 
                        help='Output file name (default: rank_changes.txt)')
    parser.add_argument('--top', type=int, default=50, 
                        help='Number of top results to display (default: 50)')
    parser.add_argument('--csv', action='store_true',
                        help='Output results as CSV files')
    args = parser.parse_args()
    
    if len(args.files) < 2:
        print("Error: At least two files are required for comparison")
        return
    
    # Load frequency data from all files
    print(f"Loading data from {len(args.files)} files...")
    freq_dicts = []
    file_names = []
    
    for file_path in args.files:
        try:
            freq_dict = load_frequency_data(file_path)
            freq_dicts.append(freq_dict)
            file_names.append(Path(file_path).name)
            print(f"  Loaded {len(freq_dict)} words from {file_path}")
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return
    
    # Convert to rank dictionaries
    print("Converting frequencies to ranks...")
    rank_dicts = [create_rank_dictionary(freq_dict) for freq_dict in freq_dicts]
    
    # Compare ranks
    print("Comparing ranks...")
    word_stats = compare_multiple_ranks(rank_dicts, file_names, args.default_rank)
    
    # Sort results by harmonic mean (lowest first)
    harmonic_sorted = sorted(word_stats, key=lambda x: x[2])
    
    # Sort results by maximum difference (highest first)
    diff_sorted = sorted(word_stats, key=lambda x: x[3], reverse=True)
    
    # Print top words by harmonic mean
    print(f"\nTop {args.top} words by harmonic mean (words ranking high across all lists):")
    header = "Word"
    for i, name in enumerate(file_names):
        header += f" | Rank in {name}"
    header += " | Harmonic Mean | Max Diff"
    print(header)
    print("-" * len(header))
    
    for word, ranks, harm_mean, max_diff in harmonic_sorted[:args.top]:
        line = f"{word}"
        for rank in ranks:
            if rank == args.default_rank:
                line += f" | {'N/A':^8}"
            else:
                line += f" | {rank:^8}"
        line += f" | {harm_mean:.2f} | {max_diff}"
        print(line)
    
    # Print top words by maximum difference
    print(f"\nTop {args.top} words by maximum rank difference:")
    print(header)
    print("-" * len(header))
    
    for word, ranks, harm_mean, max_diff in diff_sorted[:args.top]:
        line = f"{word}"
        for rank in ranks:
            if rank == args.default_rank:
                line += f" | {'N/A':^8}"
            else:
                line += f" | {rank:^8}"
        line += f" | {harm_mean:.2f} | {max_diff}"
        print(line)
    
    # Save results to files
    if args.csv:
        # Create CSV files
        harmonic_csv = Path(args.output).stem + "_harmonic.csv"
        diff_csv = Path(args.output).stem + "_diff.csv"
        
        # Create CSV headers
        csv_headers = ["Word"]
        for i, name in enumerate(file_names):
            csv_headers.append(f"Rank_{name}")
        csv_headers.extend(["Harmonic_Mean", "Max_Diff"])
        
        # Write harmonic mean sorted CSV
        with open(harmonic_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers)
            
            for word, ranks, harm_mean, max_diff in harmonic_sorted:
                row = [word]
                for rank in ranks:
                    if rank == args.default_rank:
                        row.append("N/A")
                    else:
                        row.append(rank)
                row.append(f"{harm_mean:.2f}")
                row.append(max_diff)
                writer.writerow(row)
        
        # Write max difference sorted CSV
        with open(diff_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers)
            
            for word, ranks, harm_mean, max_diff in diff_sorted:
                row = [word]
                for rank in ranks:
                    if rank == args.default_rank:
                        row.append("N/A")
                    else:
                        row.append(rank)
                row.append(f"{harm_mean:.2f}")
                row.append(max_diff)
                writer.writerow(row)
        
        print(f"\nResults saved to CSV files:")
        print(f"  - {harmonic_csv} (sorted by harmonic mean)")
        print(f"  - {diff_csv} (sorted by maximum difference)")
    else:
        # Save results to a text file
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("# Words Ranked by Harmonic Mean\n")
            f.write(header + "\n")
            f.write("-" * len(header) + "\n")
            
            for word, ranks, harm_mean, max_diff in harmonic_sorted:
                line = f"{word}"
                for rank in ranks:
                    if rank == args.default_rank:
                        line += f" | {'N/A':^8}"
                    else:
                        line += f" | {rank:^8}"
                line += f" | {harm_mean:.2f} | {max_diff}"
                f.write(line + "\n")
            
            f.write("\n\n# Words Ranked by Maximum Difference\n")
            f.write(header + "\n")
            f.write("-" * len(header) + "\n")
            
            for word, ranks, harm_mean, max_diff in diff_sorted:
                line = f"{word}"
                for rank in ranks:
                    if rank == args.default_rank:
                        line += f" | {'N/A':^8}"
                    else:
                        line += f" | {rank:^8}"
                line += f" | {harm_mean:.2f} | {max_diff}"
                f.write(line + "\n")
        
        print(f"\nComplete results saved to {args.output}")

if __name__ == "__main__":
    main()
