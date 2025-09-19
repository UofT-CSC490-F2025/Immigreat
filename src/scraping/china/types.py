from dataclasses import dataclass
from datetime import date, datetime
from typing import List


@dataclass
class PolicyDocument:
    """Data class for immigration policy documents"""
    id: str
    content: str
    source: str
    date_published: date
    language: str = 'zh-CN'
    

@dataclass
class ProcessedChunk:
    """Data class for processed document chunks with embeddings"""
    id: str
    content: str
    content_vector: List[float]
    source_document: str
    policy_section: str
    date_published: date
    chunk_index: int
    language: str = 'zh-CN'