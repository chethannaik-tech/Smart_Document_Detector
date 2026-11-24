from similarity_engine import compare_documents

text1 = """
Python is a programming language.
It is widely used in artificial intelligence
and machine learning.
"""

text2 = """
Python is a popular programming language.
It is widely used in artificial intelligence
and machine learning applications.
"""

result = compare_documents(text1, text2)

print("SIMILARITY TEST RESULT")
print("---------------------")
print("Final Score:", result["similarity_score"], "%")
print("TF-IDF:", result["tfidf_similarity"], "%")
print("Shingle:", result["shingle_similarity"], "%")
print("Sequence:", result["sequence_similarity"], "%")
print("Classification:", result["classification"])