"""
Test suite for Step 9 content generation functionality.

Tests the BasicRulesGenerator and generation API endpoints with acceptance criteria.
"""

import pytest
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock

from api.v1.gen.basic_rules import BasicRulesGenerator
from api.v1.gen.schemas import GenerateRequest


class TestBasicRulesGenerator:
    """Test the BasicRulesGenerator class."""

    @pytest.fixture
    def generator(self):
        """Create a BasicRulesGenerator instance."""
        return BasicRulesGenerator()

    @pytest.fixture
    def sample_educational_text(self):
        """Sample educational text for testing (800-1000 words)."""
        return """
        Photosynthesis is the process by which plants convert sunlight into energy. This fundamental biological process 
        occurs in the chloroplasts of plant cells and is essential for life on Earth. The equation for photosynthesis 
        is 6CO2 + 6H2O + light energy → C6H12O6 + 6O2.

        Chloroplasts are specialized organelles found in plant cells. They contain chlorophyll, which is the green 
        pigment that captures light energy. The chloroplast has two main parts: the thylakoids and the stroma. 
        Thylakoids are disk-shaped structures that contain chlorophyll and are where light reactions occur.

        The process of photosynthesis occurs in two main stages. First, the light-dependent reactions take place in 
        the thylakoid membranes. During these reactions, chlorophyll absorbs light energy and converts it into 
        chemical energy in the form of ATP and NADPH. Water molecules are split, releasing oxygen as a byproduct.

        The second stage is known as the Calvin cycle or light-independent reactions. This process takes place in 
        the stroma of the chloroplast. During the Calvin cycle, carbon dioxide is fixed into glucose using the 
        ATP and NADPH produced in the light reactions. This process requires 6 molecules of CO2 to produce 
        1 molecule of glucose.

        The efficiency of photosynthesis varies depending on several factors. Temperature affects the rate of 
        enzymatic reactions, with optimal temperatures typically ranging from 20 to 35 degrees Celsius. Light 
        intensity also plays a crucial role, with maximum efficiency usually achieved at around 2000 micromoles 
        per square meter per second.

        Carbon dioxide concentration is another limiting factor. At current atmospheric levels of approximately 
        400 parts per million, CO2 can be a limiting factor for photosynthesis. When CO2 levels increase to 
        700 ppm, photosynthetic rates can increase by 25 to 50 percent in many plant species.

        Plants have evolved different types of photosynthesis. C3 plants use the standard Calvin cycle and 
        represent about 85% of plant species. C4 plants have evolved a more efficient way to concentrate CO2 
        around the enzyme RuBisCO, allowing them to photosynthesize more efficiently in hot, dry conditions.

        The products of photosynthesis are glucose and oxygen. Glucose serves as the primary energy source for 
        plant metabolism and growth. It can be converted into starch for storage or cellulose for structural 
        support. Oxygen is released as a waste product but is essential for most life forms on Earth.

        Understanding photosynthesis is crucial for agriculture and environmental science. Farmers can optimize 
        growing conditions by managing light, temperature, and CO2 levels. Climate change research also depends 
        on understanding how plants respond to changing atmospheric conditions.
        """

    def test_generator_initialization(self, generator):
        """Test that the generator initializes properly."""
        assert generator.nlp is not None
        assert generator.nlp.lang == "en"
        assert len(generator.definition_markers) > 0
        assert len(generator.formula_patterns) > 0

    def test_keypoint_extraction(self, generator, sample_educational_text):
        """Test keypoint extraction for flashcard generation."""
        doc = generator.nlp(sample_educational_text)
        keypoints = generator._extract_keypoints(doc)
        
        assert len(keypoints) > 0
        assert any("photosynthesis" in kp["term"].lower() for kp in keypoints)
        
        for keypoint in keypoints:
            assert "term" in keypoint
            assert "definition" in keypoint
            assert "confidence" in keypoint
            assert 3 <= len(keypoint["term"]) <= 50
            assert 10 <= len(keypoint["definition"]) <= 150

    def test_numeric_fact_extraction(self, generator, sample_educational_text):
        """Test numeric fact extraction for MCQ generation."""
        doc = generator.nlp(sample_educational_text)
        numeric_facts = generator._extract_numeric_facts(doc)
        
        assert len(numeric_facts) > 0
        
        for fact in numeric_facts:
            assert "sentence" in fact
            assert "number" in fact
            assert "confidence" in fact
            assert fact["number"]["value"] > 0

    def test_cloze_generation(self, generator, sample_educational_text):
        """Test cloze question generation."""
        doc = generator.nlp(sample_educational_text)
        sentences = list(doc.sents)
        clozes = generator._generate_cloze_questions(sentences, "core", 5)
        
        assert len(clozes) > 0
        
        for cloze in clozes:
            assert cloze["type"] == "cloze"
            assert "text" in cloze["payload"]
            assert "blanks" in cloze["payload"]
            assert "___BLANK_0___" in cloze["payload"]["text"]
            assert len(cloze["payload"]["blanks"]) == 1
            assert len(cloze["payload"]["blanks"][0]["answers"]) > 0

    def test_procedure_extraction(self, generator, sample_educational_text):
        """Test procedure and formula extraction."""
        doc = generator.nlp(sample_educational_text)
        procedures = generator._extract_procedures(doc)
        
        assert len(procedures) > 0
        
        # Should find the photosynthesis equation
        formula_found = any(proc["type"] == "formula" for proc in procedures)
        assert formula_found

    def test_numeric_distractor_generation(self, generator):
        """Test heuristic distractor generation for MCQs."""
        distractors = generator._generate_numeric_distractors(100, None)
        
        assert len(distractors) > 0
        assert 100 not in distractors  # Correct answer shouldn't be in distractors
        
        # Test with unit
        unit = {"unit": "%", "type": "percentage"}
        percentage_distractors = generator._generate_numeric_distractors(75, unit)
        
        assert len(percentage_distractors) > 0
        assert 25 in percentage_distractors  # Should include complement (100-75)

    def test_quality_gates(self, generator):
        """Test quality gate filtering."""
        # Create test items with various quality issues
        test_items = [
            {  # Good item
                "type": "flashcard",
                "payload": {"front": "What is photosynthesis?", "back": "A biological process"},
                "tags": ["test"],
                "metadata": {}
            },
            {  # Too short
                "type": "flashcard",
                "payload": {"front": "?", "back": "A"},
                "tags": ["test"],
                "metadata": {}
            },
            {  # Duplicate content (same as first)
                "type": "flashcard",
                "payload": {"front": "What is photosynthesis?", "back": "A biological process"},
                "tags": ["test"],
                "metadata": {}
            },
            {  # MCQ with no correct answer
                "type": "mcq",
                "payload": {
                    "stem": "What is the formula for photosynthesis?",
                    "options": [
                        {"id": "0", "text": "Wrong A", "is_correct": False},
                        {"id": "1", "text": "Wrong B", "is_correct": False}
                    ]
                },
                "tags": ["test"],
                "metadata": {}
            }
        ]
        
        quality_items = generator._apply_quality_gates(test_items)
        
        # Should only have 1 item (first good one)
        assert len(quality_items) == 1
        assert quality_items[0]["payload"]["front"] == "What is photosynthesis?"

    def test_full_generation_pipeline(self, generator, sample_educational_text):
        """Test the complete generation pipeline (acceptance test)."""
        items = generator.generate(
            text=sample_educational_text,
            item_types=["flashcard", "mcq", "cloze", "short_answer"],
            count=15,
            difficulty="core"
        )
        
        # Acceptance criteria: 12-20 mixed items from 800-1000 words
        assert 12 <= len(items) <= 20
        
        # Check that we have mixed item types
        types_generated = {item["type"] for item in items}
        assert len(types_generated) >= 2  # At least 2 different types
        
        # All items should pass validation (>90% requirement)
        valid_items = 0
        for item in items:
            if generator._check_minimum_length(item) and generator._check_answer_clarity(item):
                valid_items += 1
        
        validation_rate = valid_items / len(items) if items else 0
        assert validation_rate >= 0.9  # >90% pass validation
        
        # Check metadata and provenance
        for item in items:
            assert "metadata" in item
            assert "provenance" in item["metadata"]
            assert "generator" in item["metadata"]["provenance"]
            assert item["metadata"]["provenance"]["generator"] == "basic_rules"

    def test_empty_input_handling(self, generator):
        """Test handling of empty or insufficient input."""
        # Empty text
        items = generator.generate(text="", count=5)
        assert len(items) == 0
        
        # Very short text
        items = generator.generate(text="Short.", count=5)
        assert len(items) == 0

    def test_difficulty_levels(self, generator, sample_educational_text):
        """Test generation with different difficulty levels."""
        for difficulty in ["intro", "core", "stretch"]:
            items = generator.generate(
                text=sample_educational_text,
                difficulty=difficulty,
                count=5
            )
            
            for item in items:
                assert item["difficulty"] == difficulty

    def test_item_type_filtering(self, generator, sample_educational_text):
        """Test generation with specific item types."""
        # Test single item type
        items = generator.generate(
            text=sample_educational_text,
            item_types=["flashcard"],
            count=10
        )
        
        for item in items:
            assert item["type"] == "flashcard"
        
        # Test multiple item types
        items = generator.generate(
            text=sample_educational_text,
            item_types=["mcq", "cloze"],
            count=10
        )
        
        types_found = {item["type"] for item in items}
        assert types_found.issubset({"mcq", "cloze"})


class TestGenerationAPI:
    """Test the generation API endpoints."""

    @pytest.fixture
    def sample_request(self):
        """Sample generation request."""
        return GenerateRequest(
            text="Photosynthesis is the process by which plants convert sunlight into energy. " * 20,
            types=["flashcard", "mcq"],
            count=10,
            difficulty="core"
        )

    @pytest.mark.asyncio
    async def test_generate_endpoint_success(self, client, sample_request):
        """Test successful content generation via API."""
        response = await client.post("/v1/items/generate", json=sample_request.dict())
        
        assert response.status_code == 200
        data = response.json()
        
        assert "generated" in data
        assert "rejected" in data
        assert "diagnostics" in data
        assert "warnings" in data
        
        # Check diagnostics structure
        diagnostics = data["diagnostics"]
        assert "input_length" in diagnostics
        assert "total_generated" in diagnostics
        assert "final_count" in diagnostics
        assert "processing_time_ms" in diagnostics

    @pytest.mark.asyncio
    async def test_generate_endpoint_validation_errors(self, client):
        """Test API validation errors."""
        # Empty request
        response = await client.post("/v1/items/generate", json={})
        assert response.status_code == 400
        
        # Invalid item type
        response = await client.post("/v1/items/generate", json={
            "text": "Sample text for testing generation",
            "types": ["invalid_type"]
        })
        assert response.status_code == 422
        
        # Invalid difficulty
        response = await client.post("/v1/items/generate", json={
            "text": "Sample text for testing generation",
            "difficulty": "invalid_difficulty"
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_endpoint_text_too_short(self, client):
        """Test API with text that's too short."""
        response = await client.post("/v1/items/generate", json={
            "text": "Short text."
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_generators_endpoint(self, client):
        """Test listing available generators."""
        response = await client.get("/v1/generators")
        
        assert response.status_code == 200
        generators = response.json()
        assert "basic_rules" in generators

    @pytest.mark.asyncio
    async def test_generator_info_endpoint(self, client):
        """Test getting generator information."""
        response = await client.get("/v1/generators/basic_rules/info")
        
        assert response.status_code == 200
        info = response.json()
        assert info["name"] == "basic_rules"
        assert info["type"] == "rule_based"
        assert "supported_item_types" in info

    @pytest.mark.asyncio
    async def test_generator_info_not_found(self, client):
        """Test getting info for non-existent generator."""
        response = await client.get("/v1/generators/nonexistent/info")
        assert response.status_code == 404


class TestAcceptanceCriteria:
    """Test Step 9 acceptance criteria."""

    @pytest.fixture
    def large_sample_text(self):
        """Large sample text (800-1000 words) for acceptance testing."""
        return """
        Machine learning is a subset of artificial intelligence that enables computers to learn and improve 
        from experience without being explicitly programmed. The field has evolved significantly since its 
        inception in the 1950s and now encompasses various algorithms and techniques.

        Supervised learning is one of the main categories of machine learning. In supervised learning, 
        algorithms learn from labeled training data to make predictions on new, unseen data. Common supervised 
        learning tasks include classification and regression. Classification involves predicting discrete 
        categories or classes, while regression involves predicting continuous numerical values.

        Linear regression is a fundamental supervised learning algorithm used for regression tasks. The 
        algorithm finds the best-fitting line through data points by minimizing the sum of squared errors. 
        The equation for simple linear regression is y = mx + b, where y is the dependent variable, x is the 
        independent variable, m is the slope, and b is the y-intercept.

        Decision trees are another popular supervised learning algorithm. They work by recursively splitting 
        the data based on feature values to create a tree-like structure. Each internal node represents a 
        feature, each branch represents a decision rule, and each leaf represents an outcome. Decision trees 
        are particularly useful because they are interpretable and can handle both numerical and categorical data.

        Random forests are an ensemble method that combines multiple decision trees. By averaging the predictions 
        of many trees, random forests typically achieve higher accuracy than individual decision trees. They 
        also reduce overfitting, which occurs when a model performs well on training data but poorly on new data.

        Support vector machines (SVMs) are powerful algorithms for both classification and regression tasks. 
        SVMs work by finding the optimal hyperplane that separates different classes with the maximum margin. 
        The algorithm uses kernel functions to handle non-linearly separable data by mapping it to a 
        higher-dimensional space.

        Unsupervised learning is another major category where algorithms find patterns in data without labeled 
        examples. Clustering is a common unsupervised learning task that groups similar data points together. 
        K-means clustering is a popular algorithm that partitions data into k clusters by minimizing the 
        within-cluster sum of squares.

        Neural networks are inspired by the structure and function of biological neurons. They consist of 
        interconnected nodes (neurons) organized in layers. Deep learning uses neural networks with many 
        hidden layers to learn complex patterns in data. Deep learning has achieved remarkable success in 
        areas such as image recognition, natural language processing, and speech recognition.

        The training process for neural networks involves forward propagation and backpropagation. Forward 
        propagation computes the output by passing inputs through the network layers. Backpropagation 
        calculates gradients and updates weights to minimize the loss function. The learning rate, typically 
        set between 0.001 and 0.1, controls how much weights are adjusted during each iteration.

        Evaluation metrics are crucial for assessing model performance. For classification tasks, common 
        metrics include accuracy, precision, recall, and F1-score. Accuracy measures the percentage of 
        correct predictions, while precision measures the percentage of positive predictions that are correct. 
        Recall measures the percentage of actual positives that are correctly identified.

        Cross-validation is a technique used to assess how well a model will generalize to new data. K-fold 
        cross-validation divides the dataset into k subsets and trains the model k times, each time using 
        k-1 subsets for training and 1 subset for validation. This provides a more robust estimate of model 
        performance than a single train-test split.

        Feature engineering is the process of selecting and transforming variables to improve model performance. 
        Good features should be relevant, informative, and not redundant. Techniques include normalization, 
        encoding categorical variables, and creating polynomial features. Feature selection methods help 
        identify the most important features and reduce dimensionality.

        """.strip()

    def test_acceptance_criteria_word_count_generation(self, large_sample_text):
        """
        Acceptance Test: From 800–1000 words, produce 12–20 mixed items; >90% pass validation.
        """
        generator = BasicRulesGenerator()
        
        # Verify input is in the right range
        word_count = len(large_sample_text.split())
        assert 800 <= word_count <= 1000, f"Sample text has {word_count} words, need 800-1000"
        
        # Generate items
        items = generator.generate(
            text=large_sample_text,
            item_types=["flashcard", "mcq", "cloze", "short_answer"],
            count=None,  # Let it decide based on text length
            difficulty="core"
        )
        
        # Should produce 12-20 mixed items
        assert 12 <= len(items) <= 20, f"Generated {len(items)} items, expected 12-20"
        
        # Should have mixed item types
        types_generated = {item["type"] for item in items}
        assert len(types_generated) >= 2, f"Only generated {types_generated}, need mixed types"
        
        # >90% should pass validation
        valid_count = 0
        for item in items:
            if (generator._check_minimum_length(item) and 
                generator._check_answer_clarity(item)):
                valid_count += 1
        
        validation_rate = valid_count / len(items)
        assert validation_rate > 0.9, f"Only {validation_rate:.1%} items passed validation, need >90%"
        
        # Items should have rejection reasons if any failed
        rejected_count = len(items) - valid_count
        if rejected_count > 0:
            # This is informational - in real API, rejected items would have reasons
            print(f"INFO: {rejected_count} items would be rejected by quality gates")

    def test_all_item_types_generated(self, large_sample_text):
        """Test that all four item types can be generated from suitable content."""
        generator = BasicRulesGenerator()
        
        for item_type in ["flashcard", "mcq", "cloze", "short_answer"]:
            items = generator.generate(
                text=large_sample_text,
                item_types=[item_type],
                count=5,
                difficulty="core"
            )
            
            assert len(items) > 0, f"No items generated for type: {item_type}"
            assert all(item["type"] == item_type for item in items)

    def test_provenance_metadata_completeness(self, large_sample_text):
        """Test that all generated items have complete provenance metadata."""
        generator = BasicRulesGenerator()
        
        items = generator.generate(
            text=large_sample_text,
            count=10,
            difficulty="core"
        )
        
        assert len(items) > 0
        
        for item in items:
            # Check required metadata fields
            assert "metadata" in item
            metadata = item["metadata"]
            
            assert "generation_method" in metadata
            assert "confidence" in metadata
            assert "provenance" in metadata
            
            # Check provenance details
            provenance = metadata["provenance"]
            assert "generator" in provenance
            assert "rule" in provenance
            assert provenance["generator"] == "basic_rules"
            
            # Should have source information
            assert ("source_text" in metadata or 
                   "source_length" in provenance), "Missing source information in provenance"