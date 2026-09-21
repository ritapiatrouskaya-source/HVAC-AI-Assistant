# ❄ HVAC Technical AI Assistant

> AI-powered assistant for HVAC technical documentation, equipment specifications, installation requirements, piping and troubleshooting.

The **HVAC Technical AI Assistant** is a Retrieval-Augmented Generation (RAG) application designed to help engineers and HVAC technicians work with technical manufacturer documentation.

The application combines structured equipment data, semantic document retrieval and an LLM to provide technical answers with references to the original documentation.

---

## 🚀 Features

### Equipment Search

Select an HVAC manufacturer, system family and model to access structured technical information.

The application provides information such as:

- Cooling capacity
- Heating capacity
- Pipe sizes
- Sound levels
- Other technical specifications

### 📄 Technical Documentation

The selected equipment can be linked directly to the corresponding page of the manufacturer's catalog.

This allows users to verify technical information against the original documentation.

### 🤖 AI Technical Assistant

Ask technical questions about the selected HVAC equipment.

The assistant uses Retrieval-Augmented Generation (RAG) to retrieve relevant information from technical documentation before generating an answer.

Example questions:

- What is the maximum interunit piping length?
- What refrigerant does this system use?
- What does error code U4 mean?
- What are the installation requirements?
- What is the operating temperature range?

### 📊 Structured Table Extraction

Technical tables in manufacturer PDFs can be difficult for conventional text-based RAG systems because PDF extraction may lose the original column relationships.

The application therefore uses table geometry and structured parsing to preserve the relationship between:

**Model → Technical Value**

This is especially important for equipment specification tables.

### 🔎 Source References

AI responses include the source document and page information used to generate the answer.

This makes the system easier to verify and more suitable for technical documentation.

---

## 🧠 How It Works

The application follows a Retrieval-Augmented Generation architecture:

```text
Manufacturer Documentation
          │
          ▼
     PDF Processing
          │
          ▼
       Chunking
          │
          ▼
   HuggingFace Embeddings
          │
          ▼
      Chroma Vector DB
          │
          ▼
     Semantic Retrieval
          │
          ├───────────────┐
          │               │
          ▼               ▼
  Selected Model      User Question
       Context             │
          │               │
          └───────┬───────┘
                  ▼
             LLM (Ollama)
                  │
                  ▼
          Technical Answer
                  │
                  ▼
          Source + Page
