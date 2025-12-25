#!/usr/bin/env python3

"""
Simple test script to verify the wordlists package works correctly.
"""

def test_imports():
    """Test that all imports work correctly."""
    try:
        from lang_lt import (
            all_words, 
            nouns_one, 
            phrases_one, 
            verbs_present,
            get_all_word_pairs_flat,
            check_for_duplicates
        )
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_data_structure():
    """Test that the data structures are properly formatted."""
    from lang_lt import all_words, get_all_word_pairs_flat
    
    # Test all_words structure
    expected_keys = {'nouns_one', 'nouns_two', 'nouns_three', 'nouns_four', 
                     'common_words', 'verbs_present', 'verbs_past', 'phrases_one'}
    actual_keys = set(all_words.keys())
    
    if expected_keys.issubset(actual_keys):
        print("✓ all_words has expected structure")
    else:
        missing = expected_keys - actual_keys
        print(f"✗ all_words missing keys: {missing}")
        return False
    
    # Test flat word pairs
    flat_words = get_all_word_pairs_flat()
    if len(flat_words) > 0:
        print(f"✓ Found {len(flat_words)} word pairs")
        
        # Check first word pair structure
        first_word = flat_words[0]
        required_keys = {'english', 'lithuanian', 'corpus', 'group'}
        if required_keys.issubset(set(first_word.keys())):
            print("✓ Word pair structure is correct")
        else:
            missing = required_keys - set(first_word.keys())
            print(f"✗ Word pair missing keys: {missing}")
            return False
    else:
        print("✗ No word pairs found")
        return False
    
    return True

def test_utility_functions():
    """Test utility functions."""
    from lang_lt import check_for_duplicates, find_missing_words
    
    # Test duplicate checking
    try:
        english_exact, english_semantic, lithuanian_exact, lithuanian_semantic = check_for_duplicates()
        print(f"✓ Duplicate check completed: {len(english_exact)} exact English duplicates found")
    except Exception as e:
        print(f"✗ Duplicate check failed: {e}")
        return False
    
    # Test missing words function
    try:
        test_words = ["house", "nonexistentword123", "car"]
        missing = find_missing_words(test_words)
        print(f"✓ Missing words check completed: {len(missing)} missing words found")
    except Exception as e:
        print(f"✗ Missing words check failed: {e}")
        return False
    
    return True

def main():
    """Run all tests."""
    print("Testing Trakaido Wordlists Package")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Data Structure Test", test_data_structure),
        ("Utility Functions Test", test_utility_functions),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
        
    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The package is ready to use.")
        return True
    else:
        print("❌ Some tests failed. Please check the issues above.")
        return False

if __name__ == "__main__":
    main()
