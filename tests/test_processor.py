"""
Tests for transcript processor module.
"""

import pytest
from limitless_lifelog.transcripts.processor import TranscriptProcessor

# Mock transcript data
MOCK_TRANSCRIPTS = [
    {
        "id": "test-id-1",
        "timestamp": "2023-05-06T14:23:15",
        "content": "I need to finish the project report by Friday and send it to the team for review.",
        "metadata": {"tags": ["work"]}
    },
    {
        "id": "test-id-2",
        "timestamp": "2023-05-06T14:25:30",
        "content": "Remember to schedule a dentist appointment for next week.",
        "metadata": {"tags": ["personal"]}
    },
    {
        "id": "test-id-3",
        "timestamp": "2023-05-06T14:30:45",
        "content": "",  # Empty content
        "metadata": {"tags": ["work"]}
    },
    {
        "id": "test-id-4",
        "timestamp": "2023-05-06T14:35:00",
        "content": "hmm",  # Too short content
        "metadata": {"tags": ["work"]}
    }
]

class TestTranscriptProcessor:
    """Test suite for TranscriptProcessor class."""
    
    def test_filter_transcripts(self):
        """Test filtering of transcripts."""
        # Initialize processor with mock LLM provider that won't be used
        # since we'll mock the _check_relevance method
        processor = TranscriptProcessor(llm_provider="none", llm_model="none")
        
        # Patch the _check_relevance method to always return True
        # This simulates the LLM check always considering transcripts relevant
        original_check = processor._check_relevance
        processor._check_relevance = lambda transcript: True
        
        try:
            filtered = processor.filter_transcripts(MOCK_TRANSCRIPTS)
            
            # Should filter out empty and too short content
            assert len(filtered) == 2
            assert filtered[0]["id"] == "test-id-1"
            assert filtered[1]["id"] == "test-id-2"
            
        finally:
            # Restore original method
            processor._check_relevance = original_check
    
    def test_load_from_path_single_file(self, tmp_path):
        """Test loading transcripts from a single file."""
        import json
        
        # Create a temporary file with mock transcript data
        file_path = tmp_path / "test_transcript.json"
        with open(file_path, 'w') as f:
            json.dump(MOCK_TRANSCRIPTS, f)
        
        processor = TranscriptProcessor(llm_provider="none", llm_model="none")
        loaded = processor.load_from_path(str(file_path))
        
        assert len(loaded) == 4
        assert loaded[0]["id"] == "test-id-1"
    
    def test_load_from_path_directory(self, tmp_path):
        """Test loading transcripts from a directory."""
        import json
        
        # Create a directory with multiple transcript files
        dir_path = tmp_path / "transcripts"
        dir_path.mkdir()
        
        # Create first file with two transcripts
        file1_path = dir_path / "transcript1.json"
        with open(file1_path, 'w') as f:
            json.dump(MOCK_TRANSCRIPTS[:2], f)
        
        # Create second file with two transcripts
        file2_path = dir_path / "transcript2.json"
        with open(file2_path, 'w') as f:
            json.dump(MOCK_TRANSCRIPTS[2:], f)
        
        processor = TranscriptProcessor(llm_provider="none", llm_model="none")
        loaded = processor.load_from_path(str(dir_path))
        
        assert len(loaded) == 4
        
    def test_load_invalid_file(self, tmp_path):
        """Test loading an invalid transcript file."""
        # Create an invalid JSON file
        file_path = tmp_path / "invalid.json"
        with open(file_path, 'w') as f:
            f.write("This is not valid JSON")
        
        processor = TranscriptProcessor(llm_provider="none", llm_model="none")
        loaded = processor.load_from_path(str(file_path))
        
        # Should return empty list for invalid file
        assert len(loaded) == 0