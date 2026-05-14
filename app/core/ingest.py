import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma

# 1. Konfiguration
PDF_ORDNER = "./leitlinien_pdfs"
DB_ORDNER = "./chroma_db"
# Leichtgewichtiges Modell für 8GB RAM [cite: 1, 281]
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2" 

def start_ingestion():
    # Embedding-Funktion initialisieren
    embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)
    
    # Text-Splitter: Chunks von ca. 1000 Zeichen 
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    
    all_documents = []
    
    # Alle PDFs im Ordner verarbeiten 
    for datei in os.listdir(PDF_ORDNER):
        if datei.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join(PDF_ORDNER, datei))
            docs = loader.load_and_split(text_splitter=splitter)
            
            # Metadaten für Zitate hinzufügen [cite: 294, 301]
            for doc in docs:
                doc.metadata["source_file"] = datei
                doc.metadata["physician_id"] = "system_default"
            
            all_documents.extend(docs)

    # In ChromaDB speichern
    vector_db = Chroma.from_documents(
        documents=all_documents,
        embedding=embeddings,
        persist_directory=DB_ORDNER
    )
    print(f"Erfolgreich {len(all_documents)} Chunks indexiert.")

if __name__ == "__main__":
    if not os.path.exists(PDF_ORDNER):
        os.makedirs(PDF_ORDNER)
    start_ingestion()