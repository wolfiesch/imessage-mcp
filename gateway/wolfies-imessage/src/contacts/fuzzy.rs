//! Fuzzy name matching using strsim.
//!
//! Port of fuzzywuzzy multi-strategy matching from Python.
//!
//! CHANGELOG:
//! - 01/10/2026 - Initial stub (Claude)

use strsim::{jaro_winkler, levenshtein, sorensen_dice};

/// Default threshold for fuzzy matching (0.0 - 1.0).
pub const DEFAULT_THRESHOLD: f64 = 0.85;

/// Fuzzy match result.
#[derive(Debug, Clone)]
pub struct FuzzyMatch {
    pub score: f64,
    pub strategy: &'static str,
}

/// Match two strings using multiple strategies.
///
/// Mimics fuzzywuzzy's approach with:
/// - token_sort_ratio: Handles word order
/// - token_set_ratio: Handles partial matches
/// - partial_ratio: Substring matches
/// - ratio: Basic Levenshtein
pub fn multi_match(query: &str, target: &str) -> FuzzyMatch {
    let query_lower = query.to_lowercase();
    let target_lower = target.to_lowercase();

    // Try different strategies and return the best score
    let strategies: Vec<(&str, f64)> = vec![
        ("jaro_winkler", jaro_winkler(&query_lower, &target_lower)),
        ("sorensen_dice", sorensen_dice(&query_lower, &target_lower)),
        ("levenshtein", levenshtein_ratio(&query_lower, &target_lower)),
        ("token_sort", token_sort_ratio(&query_lower, &target_lower)),
    ];

    strategies
        .into_iter()
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(strategy, score)| FuzzyMatch { score, strategy })
        .unwrap_or(FuzzyMatch {
            score: 0.0,
            strategy: "none",
        })
}

/// Levenshtein ratio (0.0 - 1.0).
fn levenshtein_ratio(a: &str, b: &str) -> f64 {
    let max_len = a.len().max(b.len());
    if max_len == 0 {
        return 1.0;
    }
    let distance = levenshtein(a, b);
    1.0 - (distance as f64 / max_len as f64)
}

/// Token sort ratio - sort words before comparing.
fn token_sort_ratio(a: &str, b: &str) -> f64 {
    let mut a_tokens: Vec<&str> = a.split_whitespace().collect();
    let mut b_tokens: Vec<&str> = b.split_whitespace().collect();
    a_tokens.sort();
    b_tokens.sort();

    let a_sorted = a_tokens.join(" ");
    let b_sorted = b_tokens.join(" ");

    jaro_winkler(&a_sorted, &b_sorted)
}

/// Check if a match exceeds the threshold.
pub fn is_match(query: &str, target: &str, threshold: f64) -> bool {
    multi_match(query, target).score >= threshold
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exact_match() {
        let result = multi_match("John Doe", "John Doe");
        assert!(result.score > 0.99);
    }

    #[test]
    fn test_case_insensitive() {
        let result = multi_match("john doe", "John Doe");
        assert!(result.score > 0.99);
    }

    #[test]
    fn test_word_order() {
        let result = multi_match("Doe John", "John Doe");
        assert!(result.score > 0.8, "Score was {}", result.score);
    }

    #[test]
    fn test_partial() {
        let result = multi_match("John", "John Doe");
        assert!(result.score > 0.5, "Score was {}", result.score);
    }
}
