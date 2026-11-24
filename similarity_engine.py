
import re
import math
from collections import Counter
from difflib import SequenceMatcher


def normalize_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text):
    return normalize_text(text).split()


def calculate_tf(tokens):
    counts = Counter(tokens)
    total = len(tokens)

    if total == 0:
        return {}

    return {word: count / total for word, count in counts.items()}


def calculate_idf(documents):
    total_docs = len(documents)
    document_frequency = Counter()

    for tokens in documents:
        document_frequency.update(set(tokens))

    return {
        word: math.log((total_docs + 1) / (count + 1)) + 1
        for word, count in document_frequency.items()
    }


def tfidf_vector(tokens, idf):
    tf = calculate_tf(tokens)

    return {
        word: frequency * idf.get(word, 0)
        for word, frequency in tf.items()
    }


def cosine_similarity(vector1, vector2):
    common_words = set(vector1) | set(vector2)

    if not common_words:
        return 0.0

    dot_product = sum(
        vector1.get(word, 0) * vector2.get(word, 0)
        for word in common_words
    )

    magnitude1 = math.sqrt(sum(value ** 2 for value in vector1.values()))
    magnitude2 = math.sqrt(sum(value ** 2 for value in vector2.values()))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def create_shingles(tokens, size=3):
    if len(tokens) < size:
        return set(tuple(tokens)) if tokens else set()

    return {
        tuple(tokens[i:i + size])
        for i in range(len(tokens) - size + 1)
    }


def shingle_similarity(tokens1, tokens2):
    shingles1 = create_shingles(tokens1)
    shingles2 = create_shingles(tokens2)

    union = shingles1 | shingles2

    if not union:
        return 0.0

    return len(shingles1 & shingles2) / len(union)


def sequence_similarity(text1, text2):
    return SequenceMatcher(
        None,
        normalize_text(text1),
        normalize_text(text2)
    ).ratio()


def classify_similarity(score):
    if score >= 80:
        return "Very High Similarity"
    elif score >= 60:
        return "High Similarity"
    elif score >= 40:
        return "Moderate Similarity"
    elif score >= 20:
        return "Low Similarity"
    else:
        return "Very Low Similarity"


def compare_documents(text1, text2):
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    documents = [tokens1, tokens2]
    idf = calculate_idf(documents)

    vector1 = tfidf_vector(tokens1, idf)
    vector2 = tfidf_vector(tokens2, idf)

    tfidf_score = cosine_similarity(vector1, vector2) * 100
    shingle_score = shingle_similarity(tokens1, tokens2) * 100
    sequence_score = sequence_similarity(text1, text2) * 100

    final_score = (
        tfidf_score * 0.60
        + shingle_score * 0.30
        + sequence_score * 0.10
    )

    return {
        "similarity_score": round(final_score, 2),
        "tfidf_similarity": round(tfidf_score, 2),
        "shingle_similarity": round(shingle_score, 2),
        "sequence_similarity": round(sequence_score, 2),
        "classification": classify_similarity(final_score)
    }


def compare_multiple_documents(documents):
    results = []

    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            comparison = compare_documents(
                documents[i]["text"],
                documents[j]["text"]
            )

            results.append({
                "name1": documents[i]["name"],
                "name2": documents[j]["name"],
                **comparison
            })

    return results
