# Use Python and Django for Backend Development

### The Problem
Select a backend programming language and framework to build an AI-powered university management system with complex relational data under strict time-to-delivery constraints.

### Options Considered
- **Python (Django / Django REST Framework)**
- Node.js (JavaScript) — lacks native AI/data science ecosystem; would require maintaining two separate backends (Node for web, Python for AI).
- Go / Java — high runtime performance, but excessive boilerplate and development overhead would delay project delivery.

### Rationale
- **Unified Web and AI Ecosystem:** The system requires AI features (automated grading, attendance predictions, chatbots) powered by PyTorch, OpenAI, LangChain, and Pandas. Python allows running the core web application and AI workloads in the exact same runtime without extra server bridges and deployment complexity.
- **Rapid Relational Data Modeling & Admin Interface:** Managing intricate university data relationships (students, courses, grades, departments, fees) is streamlined by Django's ORM and ready-to-use Admin Panel, saving weeks of development time.

### Notes
- **Performance & GIL Mitigation:** To overcome Python's slower interpreted execution and Global Interpreter Lock (GIL) during heavy math and CPU operations, intensive AI calculations, PDF reports, and bulk emails are offloaded to background workers (Celery + Redis), keeping the web server responsive.
- References:
  - [Django Documentation](https://docs.djangoproject.com/)
  - [Django REST Framework](https://www.django-rest-framework.org/)
  - [Open edX Developer Documentation](https://docs.openedx.org/)
  - [Meta Engineering Blog](https://engineering.fb.com/)

