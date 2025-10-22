"""
Simple Vector Database Tool using ChromaDB for device storage and retrieval.
"""
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
    print("Using pysqlite3 for sqlite3.")
except ImportError:
    print("pysqlite3 not found or failed to import, falling back to default sqlite3.")
    pass
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


class VectorDBTool:
    """Vector database tool for storing and retrieving device information."""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Initialize ChromaDB with persistence."""
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Create or get collection for devices
        self.collection = self.client.get_or_create_collection(
            name="devices",
            metadata={"hnsw:space": "cosine"}
        )
    
    def add_devices(
        self,
        devices: List[Dict[str, Any]],
        category: str,
        location: str
    ) -> int:
        """
        Add devices to the vector database.
        
        Args:
            devices: List of device dictionaries with specs and details
            category: Device category (phone, laptop, tablet, etc.)
            location: Location where devices are available
            
        Returns:
            Number of devices added
        """
        if not devices:
            return 0
        
        documents = []
        metadatas = []
        ids = []
        
        timestamp = datetime.utcnow().isoformat()
        
        for i, device in enumerate(devices):
            # Create searchable text content
            content = f"{device.get('name', '')} {device.get('brand', '')} "
            content += f"{json.dumps(device.get('specs', {}))}"
            
            documents.append(content)
            
            # Store metadata for filtering
            metadata = {
                "category": category,
                "location": location,
                "name": device.get("name", ""),
                "brand": device.get("brand", ""),
                "price": device.get("price", 0),
                "vendor": device.get("vendor", ""),
                "url": device.get("url", ""),
                "indexed_at": timestamp,
                "specs": json.dumps(device.get("specs", {})),
                "physical_store": device.get("physical_store", ""),
                "store_contact": device.get("store_contact", "")
            }
            metadatas.append(metadata)
            
            # Create unique ID
            device_id = f"{category}_{location}_{device.get('name', '')}_{i}_{timestamp}"
            ids.append(device_id.replace(" ", "_").lower())
        
        # --- Sanitize metadata values to ensure ChromaDB compatibility ---
        sanitized_metadatas = []
        for metadata in metadatas:
            clean_meta = {}
            for k, v in metadata.items():
                # Replace None with empty string or 0 (depending on type)
                if v is None:
                    clean_meta[k] = ""  # or 0 if numeric
                elif isinstance(v, list):
                    clean_meta[k] = ", ".join(map(str, v))
                elif isinstance(v, dict):
                    # Recursively remove None inside dicts before dumping
                    safe_dict = {ik: ("" if iv is None else iv) for ik, iv in v.items()}
                    clean_meta[k] = json.dumps(safe_dict, ensure_ascii=False)
                elif isinstance(v, (set, tuple)):
                    clean_meta[k] = ", ".join(map(str, v))
                else:
                    clean_meta[k] = v
            sanitized_metadatas.append(clean_meta)

        # --- Add to ChromaDB ---
        self.collection.add(
            documents=documents,
            metadatas=sanitized_metadatas,
            ids=ids
        )

        
        return len(devices)
    
    def query_devices(
        self,
        query: str,
        category: str,
        location: str,
        price_max: Optional[float] = None,
        price_min: Optional[float] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query devices from the vector database.
        
        Args:
            query: Natural language query about device requirements
            category: Device category to filter
            location: Location to filter
            price_max: Maximum price filter
            price_min: Minimum price filter
            top_k: Number of results to return
            
        Returns:
            List of matching devices with metadata
        """
        # Build where filter
        where_filter = {
            "$and": [
                {"category": {"$eq": category}},
                {"location": {"$eq": location}}
            ]
        }
        
        # Add price filters if provided
        if price_max is not None:
            where_filter["$and"].append({"price": {"$lte": price_max}})
        if price_min is not None:
            where_filter["$and"].append({"price": {"$gte": price_min}})
        
        # Query the collection
        results = self.collection.query(
            query_texts=[query],
            where=where_filter,
            n_results=top_k
        )
        
        # Format results
        devices = []
        if results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i]
                device = {
                    "id": doc_id,
                    "name": metadata.get("name"),
                    "brand": metadata.get("brand"),
                    "price": metadata.get("price"),
                    "vendor": metadata.get("vendor"),
                    "url": metadata.get("url"),
                    "specs": json.loads(metadata.get("specs", "{}")),
                    "physical_store": metadata.get("physical_store"),
                    "store_contact": metadata.get("store_contact"),
                    "indexed_at": metadata.get("indexed_at"),
                    "similarity_score": 1 - results['distances'][0][i]  # Convert distance to similarity
                }
                devices.append(device)
        
        return devices
    
    def cleanup_old_devices(self, category: str, days_old: int = 30) -> int:
        """
        Remove devices older than specified days.
        Uses ISO datetime strings safely (string comparison on UTC format).
        """
        from datetime import timedelta

        cutoff_date = (datetime.utcnow() - timedelta(days=days_old)).isoformat()

        try:
            # String-based ISO comparisons work because ISO8601 timestamps are lexicographically sortable
            results = self.collection.get(
                where={
                    "$and": [
                        {"category": {"$eq": category}},
                        {"indexed_at": {"$lt": cutoff_date}}
                    ]
                }
            )
        except Exception as e:
            print(f"[WARN] Cleanup query failed: {e}")
            return 0

        if results.get("ids"):
            self.collection.delete(ids=results["ids"])
            print(f"🧹 Cleaned up {len(results['ids'])} old '{category}' devices.")
            return len(results["ids"])

        return 0

    
    def get_device_count(self, category: Optional[str] = None) -> int:
        """Get total device count, optionally filtered by category."""
        where_filter = {"category": {"$eq": category}} if category else None
        results = self.collection.get(where=where_filter)
        return len(results['ids'])


# Example usage
if __name__ == "__main__":
    # Initialize tool
    db_tool = VectorDBTool()
    
    # Add sample devices
    sample_phones = [
        {
            "name": "Samsung Galaxy A35 5G",
            "brand": "Samsung",
            "price": 42999,
            "vendor": "Jumia Kenya",
            "url": "https://www.jumia.co.ke/samsung-a35-5g/",
            "specs": {
                "ram": "8GB",
                "storage": "128GB",
                "processor": "Exynos 1380",
                "battery": "5000mAh"
            },
            "physical_store": "Mary and Beth Tech, Tom Mboya Street",
            "store_contact": "0765743998"
        }
    ]
    
    # Add to database
    count = db_tool.add_devices(sample_phones, "phone", "Nairobi, KE")
    print(f"Added {count} devices")
    
    # Query devices
    results = db_tool.query_devices(
        query="8GB RAM smartphone under 45000",
        category="phone",
        location="Nairobi, KE",
        price_max=45000,
        top_k=5
    )
    
    print(f"\nFound {len(results)} matching devices:")
    for device in results:
        print(f"- {device['name']}: KES {device['price']} (similarity: {device['similarity_score']:.2f})")