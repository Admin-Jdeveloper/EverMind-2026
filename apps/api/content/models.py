import uuid
from django.db import models
from django.conf import settings
from pgvector.django import VectorField, HnswIndex

class Collection(models.Model):
    """User-owned folder/collection for organizing saved items."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_private = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [['user', 'name']]

    def __str__(self):
        return f"{self.user.email} - {self.name}"

class Tag(models.Model):
    """User-scoped label for categorizing saved items."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=16, default='#3B82F6')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [['user', 'name']]

    def __str__(self):
        return self.name

class ContentItem(models.Model):
    """Canonical saved digital content item (URL, document, note)."""
    
    TYPE_URL = 'url'
    TYPE_NOTE = 'note'
    TYPE_DOCUMENT = 'document'
    TYPE_VIDEO = 'video'
    TYPE_CHOICES = [
        (TYPE_URL, 'URL / Web Page'),
        (TYPE_NOTE, 'Plain Note'),
        (TYPE_DOCUMENT, 'Uploaded Document'),
        (TYPE_VIDEO, 'Video / YouTube'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_EXTRACTING = 'extracting'
    STATUS_CHUNKING = 'chunking'
    STATUS_EMBEDDING = 'embedding'
    STATUS_INDEXING = 'indexing'
    STATUS_COMPLETED = 'completed'
    STATUS_PARTIAL = 'partial'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_EXTRACTING, 'Extracting'),
        (STATUS_CHUNKING, 'Chunking'),
        (STATUS_EMBEDDING, 'Generating Embeddings'),
        (STATUS_INDEXING, 'Vector Indexing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_PARTIAL, 'Metadata Only / Partial'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_items')
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    tags = models.ManyToManyField(Tag, blank=True, related_name='items')
    
    content_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TYPE_URL)
    title = models.CharField(max_length=512, blank=True)
    source_url = models.URLField(max_length=2048, blank=True)
    summary = models.TextField(blank=True)
    raw_text = models.TextField(blank=True)
    file_key = models.CharField(max_length=1024, blank=True, help_text="MinIO S3 object storage key")
    
    ingestion_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Canonical versioning and integrity hash
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, help_text="SHA-256 hash of extracted canonical text")
    version = models.PositiveIntegerField(default=1, help_text="Monotonically increasing content version")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or self.source_url or str(self.id)

class ContentChunk(models.Model):
    """Text chunk derived from ContentItem with pgvector embedding for semantic retrieval."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    
    # pgvector embedding: 384 dimensions matches sentence-transformers/all-MiniLM-L6-v2
    embedding = VectorField(dimensions=384, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, help_text="SHA-256 hash of chunk text")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['content_item', 'chunk_index']
        unique_together = [['content_item', 'chunk_index']]
        indexes = [
            HnswIndex(
                name='chunk_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            )
        ]

    def __str__(self):
        return f"{self.content_item_id} chunk #{self.chunk_index}"

class ContentFact(models.Model):
    """
    Structured entity-attribute-value fact extracted deterministically from canonical source content.
    Provides authoritative, traceable exact-value retrieval (e.g., DOB, dates, identifiers, amounts).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='facts')
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='facts')
    content_chunk = models.ForeignKey(ContentChunk, on_delete=models.CASCADE, null=True, blank=True, related_name='facts')
    
    entity = models.CharField(max_length=128, default="general", db_index=True)
    attribute = models.CharField(max_length=128, db_index=True)
    fact_key = models.CharField(max_length=128, db_index=True, help_text="Normalized lookup key (e.g. 'dob', 'date_of_birth')")
    exact_value = models.TextField(help_text="Exact literal value extracted from source text")
    
    source_location = models.JSONField(default=dict, blank=True, help_text="Page, slide, row, or timestamp metadata")
    confidence = models.FloatField(default=1.0)
    version = models.PositiveIntegerField(default=1)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'fact_key']),
            models.Index(fields=['user', 'attribute']),
            models.Index(fields=['content_item']),
        ]

    def __str__(self):
        return f"[{self.user_id}] {self.attribute}: {self.exact_value[:30]}"

class SavedSearch(models.Model):
    """User-saved search query with filter criteria and alert preferences."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_searches')
    name = models.CharField(max_length=255)
    query_text = models.CharField(max_length=1024)
    filters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.name} ('{self.query_text}')"

