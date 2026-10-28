import chromadb

client = chromadb.PersistentClient(path="./chroma_engram")
try:
    client.delete_collection("response_cache")
    print("Коллекция response_cache удалена")
except:
    pass

# Создаём заново пустую
client.get_or_create_collection("response_cache", metadata={"hnsw:space": "cosine"})
print("Новая пустая коллекция создана")