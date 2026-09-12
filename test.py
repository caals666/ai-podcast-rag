import ast

keywords = ['Channel inactivity after house move','Burnout over teaching programming','Survey to guide future content', 'Commitment to high‑quality education', 'Thank you and encouragement to respond']

raw = ''
with open('transcript.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

# Find the dict inside the file (skip any [file name]: / [file content begin] headers)
start = raw.find('{')
end = raw.rfind('}') + 1

segment_texts = []
if start != -1 and end > start:
    dict_str = raw[start:end]
    try:
        content = ast.literal_eval(dict_str)
        if isinstance(content, dict) and 'segments' in content:
            segment_texts = [seg['text'] for seg in content['segments']]
    except (ValueError, SyntaxError):
        pass

# Fallback: treat whole file as plain text (only runs if dict parsing failed)
if not segment_texts:
    words = raw.split()
    segment_texts = [" ".join(words[i:i + 25]) for i in range(0, len(words), 25)]


# Here we are importing the SentenceTransformer class to load pre-trained models
# and util for similarity functions like cosine similarity
from sentence_transformers import SentenceTransformer, util

# After import the require librariries, we are loading a pre-trained model that can turn sentences into vector embeddings
# This model is coming from huggingface, which is light but fast to capture good semantic meaning
model = SentenceTransformer('all-MiniLM-L6-v2')

# Define FAQs - Here we are taking a example list of FAQ sentences that users might ask on a website and possible answers we'll search through

# Than we convert each FAQ into an embedding vector (a numeric representation of meaning)
faq_embeddings = model.encode(segment_texts)

# Here we are taking the User query, which is also encoded into another embedding vector
query = "Job market future"
query_embedding = model.encode(query)

# Here 'cos_sim' Compares and compute similarity scores for the query embedding with every FAQ embedding using cosine similarity (a measure of closeness between vectors)
# Higher scores mean higher semantic similarity.
cosine_scores = util.cos_sim(query_embedding, faq_embeddings)

# Here 'argmax()' helps to find best match by finding the FAQ with the highest similarity score
best_match_idx = cosine_scores.argmax()

# Prints the query and the closest matching FAQ
print("Query:", query)
print("Best Match:", segment_texts[best_match_idx])

# Further we can fetch the similarity score and print the score as well
best_score = cosine_scores[0][best_match_idx].item()  # extract float
print("Cosine similarity score between these sentences:", round(best_score,3))