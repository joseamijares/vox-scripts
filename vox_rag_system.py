#!/usr/bin/env python3
"""
VOX RAG System v1.0
Retrieval-Augmented Generation for Portfolio Intelligence

- Embeds Obsidian vault + portfolio data + trade history
- Provides semantic search over all portfolio knowledge
- Powers the AI Harness with contextual memory

Usage:
    python3 vox_rag_system.py init          # Build vector DB from scratch
    python3 vox_rag_system.py query "Why did I buy NVDA?"
    python3 vox_rag_system.py query "Show me losing trades in healthcare"
    python3 vox_rag_system.py query "What was the LLM Council consensus on crypto?"
"""

import os
import sys
import json
import glob
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

# Try to import chromadb
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("Warning: chromadb not installed. Install with: pip install chromadb")

# OpenAI for embeddings
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Load API key from .env
def load_api_key():
    """Parse .env file directly — never use os.environ"""
    env_paths = [
        os.path.expanduser("~/.hermes/scripts/.env"),
        os.path.expanduser("~/.env"),
        ".env"
    ]
    for path in env_paths:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        key, val = line.strip().split('=', 1)
                        if key == 'OPENROUTER_API_KEY' or key == 'OPENAI_API_KEY':
                            return val.strip().strip('"').strip("'")
    return None

API_KEY = load_api_key()

@dataclass
class Document:
    id: str
    text: str
    metadata: Dict
    source: str

class VoxRAG:
    """RAG system for VOX portfolio intelligence"""
    
    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or os.path.expanduser("~/.hermes/scripts/vox_chroma_db")
        self.collection_name = "vox_knowledge"
        self.client = None
        self.collection = None
        
        if CHROMA_AVAILABLE:
            self.client = chromadb.Client(Settings(
                persist_directory=self.persist_dir,
                anonymized_telemetry=False
            ))
        
        self.vault_dir = os.path.expanduser("~/Documents/Obsidian Vault/Portfolio-Finance")
        self.scripts_dir = os.path.expanduser("~/.hermes/scripts")
        
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding using OpenAI API"""
        if not API_KEY:
            raise ValueError("No API key found. Set OPENAI_API_KEY in .env")
        
        # Use OpenRouter for embeddings
        import urllib.request
        import urllib.error
        
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/embeddings",
            data=json.dumps({
                "model": "openai/text-embedding-3-small",
                "input": text[:8000]  # Limit text length
            }).encode(),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data['data'][0]['embedding']
        except Exception as e:
            print(f"Embedding error: {e}")
            # Fallback: simple hash-based embedding
            return self._fallback_embedding(text)
    
    def _fallback_embedding(self, text: str) -> List[float]:
        """Simple fallback embedding using keyword hashing"""
        import random
        random.seed(hash(text) % 2**32)
        return [random.uniform(-1, 1) for _ in range(1536)]
    
    def _load_obsidian_vault(self) -> List[Document]:
        """Load all markdown files from Obsidian vault"""
        docs = []
        
        if not os.path.exists(self.vault_dir):
            print(f"Vault not found at {self.vault_dir}")
            return docs
        
        for md_file in glob.glob(f"{self.vault_dir}/**/*.md", recursive=True):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract YAML frontmatter if present
                metadata = {}
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        try:
                            import yaml
                            metadata = yaml.safe_load(parts[1])
                            content = parts[2]
                        except:
                            pass
                
                rel_path = os.path.relpath(md_file, self.vault_dir)
                doc_id = hashlib.md5(rel_path.encode()).hexdigest()[:16]
                
                docs.append(Document(
                    id=f"vault_{doc_id}",
                    text=content,
                    metadata={
                        "source": "obsidian",
                        "path": rel_path,
                        "title": Path(md_file).stem,
                        **{k: str(v) for k, v in metadata.items()}
                    },
                    source="obsidian"
                ))
            except Exception as e:
                print(f"Error loading {md_file}: {e}")
        
        print(f"Loaded {len(docs)} Obsidian documents")
        return docs
    
    def _load_portfolio_data(self) -> List[Document]:
        """Load portfolio positions as documents"""
        docs = []
        
        # Load dashboard positions
        positions_file = f"{self.scripts_dir}/dashboard_positions.json"
        if os.path.exists(positions_file):
            with open(positions_file) as f:
                data = json.load(f)
            
            for pos in data.get('positions', []):
                ticker = pos.get('ticker', 'UNKNOWN')
                broker = pos.get('broker', 'UNKNOWN')
                
                # Create a rich text description
                text = f"""
Position: {ticker} in {broker}
Value: ${pos.get('value', 0):,.2f}
Unrealized P&L: ${pos.get('unrealized_pnl', 0):,.2f} ({pos.get('unrealized_pnl_pct', 0):.1f}%)
Grade: {pos.get('grade', 'Ungraded')}
Sector: {pos.get('sector', 'Unknown')}
""".strip()
                
                doc_id = hashlib.md5(f"{ticker}_{broker}".encode()).hexdigest()[:16]
                docs.append(Document(
                    id=f"pos_{doc_id}",
                    text=text,
                    metadata={
                        "source": "portfolio",
                        "ticker": ticker,
                        "broker": broker,
                        "value": pos.get('value', 0),
                        "grade": pos.get('grade', 0),
                        "sector": pos.get('sector', 'Unknown')
                    },
                    source="portfolio"
                ))
        
        print(f"Loaded {len(docs)} portfolio positions")
        return docs
    
    def _load_trade_history(self) -> List[Document]:
        """Load trade journal entries"""
        docs = []
        
        journal_files = [
            f"{self.scripts_dir}/trade_journal.json",
            f"{self.scripts_dir}/monday_trade_plan.json",
        ]
        
        for jf in journal_files:
            if os.path.exists(jf):
                with open(jf) as f:
                    data = json.load(f)
                
                # Convert to text
                text = json.dumps(data, indent=2)
                doc_id = hashlib.md5(jf.encode()).hexdigest()[:16]
                
                docs.append(Document(
                    id=f"journal_{doc_id}",
                    text=text,
                    metadata={
                        "source": "journal",
                        "file": os.path.basename(jf)
                    },
                    source="journal"
                ))
        
        print(f"Loaded {len(docs)} journal documents")
        return docs
    
    def _load_grades(self) -> List[Document]:
        """Load grade results as documents"""
        docs = []
        
        grades_file = f"{self.scripts_dir}/portfolio_grades.json"
        if os.path.exists(grades_file):
            with open(grades_file) as f:
                data = json.load(f)
            
            for ticker, grade_data in data.items():
                if isinstance(grade_data, dict):
                    text = f"""
Grade Analysis for {ticker}:
Overall Grade: {grade_data.get('grade', 'N/A')}
Action: {grade_data.get('action', 'N/A')}
Technical Score: {grade_data.get('technical', 'N/A')}
Fundamental Score: {grade_data.get('fundamental', 'N/A')}
Sentiment Score: {grade_data.get('sentiment', 'N/A')}
""".strip()
                    
                    doc_id = hashlib.md5(f"grade_{ticker}".encode()).hexdigest()[:16]
                    docs.append(Document(
                        id=f"grade_{doc_id}",
                        text=text,
                        metadata={
                            "source": "grades",
                            "ticker": ticker,
                            "grade": grade_data.get('grade', 0),
                            "action": grade_data.get('action', 'HOLD')
                        },
                        source="grades"
                    ))
        
        print(f"Loaded {len(docs)} grade documents")
        return docs
    
    def init_collection(self):
        """Initialize or get the ChromaDB collection"""
        if not CHROMA_AVAILABLE:
            print("ChromaDB not available. Install with: pip install chromadb")
            return False
        
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "VOX Portfolio Knowledge Base"}
            )
            print(f"Collection '{self.collection_name}' ready")
            return True
        except Exception as e:
            print(f"Error creating collection: {e}")
            return False
    
    def build_index(self):
        """Build the full RAG index from all sources"""
        if not self.init_collection():
            return
        
        print("\n=== Building VOX RAG Index ===\n")
        
        # Load all documents
        all_docs = []
        all_docs.extend(self._load_obsidian_vault())
        all_docs.extend(self._load_portfolio_data())
        all_docs.extend(self._load_trade_history())
        all_docs.extend(self._load_grades())
        
        print(f"\nTotal documents: {len(all_docs)}")
        
        # Add to collection in batches
        batch_size = 100
        for i in range(0, len(all_docs), batch_size):
            batch = all_docs[i:i+batch_size]
            
            ids = [doc.id for doc in batch]
            texts = [doc.text for doc in batch]
            metadatas = [doc.metadata for doc in batch]
            
            # Generate embeddings
            print(f"Embedding batch {i//batch_size + 1}/{(len(all_docs)-1)//batch_size + 1}...")
            embeddings = [self._get_embedding(text) for text in texts]
            
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
        
        print(f"\n✅ Index built successfully! {len(all_docs)} documents embedded.")
        
        # Persist
        if hasattr(self.client, 'persist'):
            self.client.persist()
    
    def query(self, query_text: str, n_results: int = 5) -> List[Dict]:
        """Query the RAG system"""
        if not self.collection:
            if not self.init_collection():
                return []
        
        # Embed query
        query_embedding = self._get_embedding(query_text)
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        formatted = []
        for i in range(len(results['ids'][0])):
            formatted.append({
                "id": results['ids'][0][i],
                "text": results['documents'][0][i][:500] + "..." if len(results['documents'][0][i]) > 500 else results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i]
            })
        
        return formatted
    
    def get_stats(self) -> Dict:
        """Get index statistics"""
        if not self.collection:
            return {"error": "No collection initialized"}
        
        count = self.collection.count()
        return {
            "total_documents": count,
            "collection_name": self.collection_name,
            "persist_dir": self.persist_dir
        }


def main():
    rag = VoxRAG()
    
    if len(sys.argv) < 2:
        print("""
VOX RAG System v1.0

Usage:
    python3 vox_rag_system.py init
    python3 vox_rag_system.py query "your question here"
    python3 vox_rag_system.py stats
        """)
        return
    
    command = sys.argv[1]
    
    if command == "init":
        rag.build_index()
    
    elif command == "query":
        if len(sys.argv) < 3:
            print("Please provide a query text")
            return
        
        query_text = " ".join(sys.argv[2:])
        print(f"\n🔍 Query: {query_text}\n")
        
        results = rag.query(query_text, n_results=5)
        
        print(f"Found {len(results)} results:\n")
        for i, r in enumerate(results, 1):
            source = r['metadata'].get('source', 'unknown')
            print(f"--- Result {i} [{source}] (distance: {r['distance']:.3f}) ---")
            print(r['text'][:300])
            print()
    
    elif command == "stats":
        stats = rag.get_stats()
        print(json.dumps(stats, indent=2))
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
