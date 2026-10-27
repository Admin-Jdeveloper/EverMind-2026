from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CollectionViewSet,
    TagViewSet,
    ContentItemViewSet,
    SavedSearchViewSet,
    IngestUrlView,
    IngestNoteView,
    UploadDocumentView,
    ReembedAPIView,
    WebClipAPIView,
    LibraryExportAPIView,
    LibraryBulkImportAPIView
)

router = DefaultRouter()
router.register(r'collections', CollectionViewSet, basename='collection')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'saved-searches', SavedSearchViewSet, basename='saved-search')
router.register(r'items', ContentItemViewSet, basename='content-item')

urlpatterns = [
    path('urls/', IngestUrlView.as_view(), name='ingest-url'),
    path('notes/', IngestNoteView.as_view(), name='ingest-note'),
    path('files/', UploadDocumentView.as_view(), name='upload-document'),
    path('clip/', WebClipAPIView.as_view(), name='content-clip'),
    path('export/', LibraryExportAPIView.as_view(), name='library-export'),
    path('import-bulk/', LibraryBulkImportAPIView.as_view(), name='library-import-bulk'),
    path('reembed/', ReembedAPIView.as_view(), name='content-reembed'),
    path('', include(router.urls)),
]
