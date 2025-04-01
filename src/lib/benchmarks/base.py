#!/usr/bin/python3

"""Base classes for implementing language model benchmarks."""

# BenchmarkRunner formerly in this file; imported for imports but not used locally
from lib.benchmarks.base_runner import BenchmarkRunner
from lib.benchmarks.base_generator import BenchmarkGenerator    

COMMON_SHORT_WORDS = [
    "chair", "music", "candle", "tree", "cat", "fish", "sun", "book", "ball",
    "hat", "water", "cake", "baby", "flower", "hill", "road", "clock", "door",
    "farm", "game", "hand", "ice", "jelly", "key", "moon", "nest", "orange", 
    "park", "quiet", "red", "sock"
]

COMMON_MEDIUM_WORDS = [
    'abundance', 'appearance', 'banana', 'beautiful', 'challenge', 'computer',
    'delicious', 'difficult', 'education', 'elephant', 'fantastic', 'freedom',
    'garden', 'generation', 'happiness', 'important', 'internet', 'jewelry',
    'journey', 'knowledge', 'language', 'magazine', 'mountain', 'notebook',
    'ocean', 'operation', 'patience', 'positive', 'question', 'rainbow', 'reaction',
    'science', 'solution', 'technology', 'telephone', 'umbrella', 'universe',
    'victory', 'window', 'wonderful', 'yesterday', 'zealous'
]

COMMON_LONG_WORDS = [
    "strawberry", "programming", "mathematics", "engineering", "intelligence",
    "development", "application", "successful", "interesting", "beautiful",
    "ordinary", "atmosphere", "excitement", "conversation", "experience",
    "knowledge", "necessary", "community", "education", "information",
    "technology", "understanding", "opportunity", "relationship", "environment",
    "significant", "performance", "profession", "university", "restaurant",
    "breakfast", "president", "television", "government", "important",
    "computer", "different", "business", "possible", "together"
]

COUNTRIES = [
    "United States", "Canada", "Mexico", "Brazil", "Argentina", "United Kingdom", "France", "Germany", "Italy", "Spain",
    "Portugal", "Netherlands", "Belgium", "Switzerland", "Sweden", "Norway", "Denmark", "Finland", "Poland", "Czech Republic",
    "Austria", "Hungary", "Greece", "Turkey", "Russia", "China", "Japan", "South Korea", "India", "Indonesia",
    "Thailand", "Vietnam", "Philippines", "Australia", "New Zealand", "South Africa", "Egypt", "Nigeria", "Kenya", "Ethiopia",
    "Saudi Arabia", "United Arab Emirates", "Pakistan", "Bangladesh", "Malaysia", "Singapore", "Chile", "Colombia"
]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Miami", "Toronto", "Vancouver", "Mexico City", "São Paulo", "Buenos Aires",
    "London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Brussels", "Vienna", "Stockholm", "Copenhagen",
    "Oslo", "Helsinki", "Warsaw", "Prague", "Budapest", "Athens", "Istanbul", "Moscow", "Saint Petersburg", "Beijing",
    "Shanghai", "Hong Kong", "Tokyo", "Osaka", "Seoul", "Bangkok", "Hanoi", "Jakarta", "Manila", "Kuala Lumpur",
    "Singapore", "Sydney", "Melbourne", "Brisbane", "Cape Town", "Johannesburg", "Cairo", "Lagos", "Nairobi", "Addis Ababa",
    "Riyadh", "Dubai", "Abu Dhabi", "Tel Aviv", "Tehran", "Baghdad", "Karachi", "Lahore", "Dhaka", "Mumbai",
    "Delhi", "Bangalore", "Chennai", "Kolkata", "Rio de Janeiro", "Bogotá", "Santiago", "Lima", "Caracas", "Quito",
    "San Francisco", "Boston", "Washington, D.C.", "Seattle", "Dallas", "Atlanta", "Montreal", "Guadalajara"
]

MOUNTAINS = [
    "Mount Everest", "Kangchenjunga", "Lhotse", "Makalu", "Cho Oyu", "Dhaulagiri", "Manaslu", "Nanga Parbat", "Annapurna",
    "Mount Elbrus", "Mont Blanc", "Matterhorn", "Eiger", "Monte Rosa", "Pico de Orizaba", "Popocatépetl", "Mount Logan", "Denali", "Mount Saint Elias",
    "Mount Vinson", "Aconcagua", "Mount Kosciuszko", "Mauna Kea", "Mauna Loa", "Mount Kilimanjaro", "Mount Kenya", "Ras Dashen", "Mount Stanley", "Mount Wilhelm",
    "Mount Rainier", "Mount Shasta", "Mount Hood", "Mount Whitney", "Grand Teton", "Mount Washington", "Ben Nevis", "Carrauntoohil", "Mount Cook",
    "Mount Ruapehu", "Damavand", "Zugspitze", "Jungfrau", "Mount Kinabalu", "Gunnbjørn Fjeld", "Mount Erebus"
]

RIVERS = [
    "Amazon", "Nile", "Mississippi", "Yangtze", "Yellow", "Congo", "Mekong", "Ganges", "Danube", "Volga",
    "Rhine", "Seine", "Thames", "Tiber", "Loire", "Elbe", "Oder", "Dnieper", "Don", "Ural",
    "Ob", "Yenisei", "Lena", "Amur", "Indus", "Brahmaputra", "Salween", "Irrawaddy", "Murray", "Darling",
    "Colorado", "Columbia", "St. Lawrence", "Orinoco", "Paraná", "Zambezi", "Niger", "Tigris", "Euphrates"
]

# List of common animals
ANIMALS = [
    "alligator", "bear", "cat", "cheetah", "chimpanzee", "cow", "crocodile", "deer", "dog", "dolphin",
    "elephant", "fox", "giraffe", "goat", "gorilla", "hippopotamus", "horse", "kangaroo", "koala", "leopard",
    "lion", "monkey", "panda", "pig", "rabbit", "rhinoceros", "sheep", "tiger", "wolf", "zebra"
]

# List of common colors
COLORS = [
    "red", "blue", "green", "yellow", "purple", "orange", "pink", "brown", "black", "white",
    "gray", "cyan", "magenta", "violet", "indigo", "gold", "silver", "beige", "teal", "navy"
]

# List of common foods
FOODS = [
    "pizza", "burger", "pasta", "salad", "sushi", "sandwich", "taco", "cake", "ice cream", "chocolate",
    "fruit", "vegetable", "rice", "bread", "cheese", "egg", "chicken", "fish", "steak", "seafood",
    "soup", "cereal", "oatmeal", "pie", "cookie", "donut", "waffle"
]