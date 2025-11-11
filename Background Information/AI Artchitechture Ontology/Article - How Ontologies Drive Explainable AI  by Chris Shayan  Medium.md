---
created: 2025-10-29T01:02:14 (UTC -05:00)
tags: []
source: https://christophershayan.medium.com/how-ontologies-drive-explainable-ai-e6ba7a7d6643
author: Chris Shayan
---

# How Ontologies Drive Explainable AI | by Chris Shayan | Medium

> ## Excerpt
> How Ontologies Drive Explainable AI This blog post goes into the intricate relationship between ontologies and explainable AI, adopting a perspective deeply rooted in ontological principles. The …

---
[

![Chris Shayan](https://miro.medium.com/v2/resize:fill:32:32/1*GBTGt3ZIu8QMf-rxDxsLjg@2x.jpeg)



](https://christophershayan.medium.com/?source=post_page---byline--e6ba7a7d6643---------------------------------------)

> This blog post goes into the intricate relationship between ontologies and explainable AI, adopting a perspective deeply rooted in ontological principles. The concepts discussed herein are inherently philosophical and may require a foundational understanding of knowledge representation, formal semantics, and logical inference. While I will strive for clarity, the subject matter is advanced and may be most relevant to readers with a strong background in ontology, knowledge engineering, and semantic technologies.

Press enter or click to view image in full size

![](https://miro.medium.com/v2/resize:fit:700/1*onkpyqCWmPUI1f5Cp0stDg.png)

Image Source: mastechinfotrellis

Increased AI deployment in critical sectors demands transparency and accountability, driven by regulatory scrutiny. Trust in AI necessitates understanding its reasoning, especially in high-stakes domains. Consider, for instance, the stringent requirements emerging from GDPR’s “right to explanation” and similar frameworks being debated and implemented across various jurisdictions. This isn’t simply about satisfying compliance; it’s about fostering genuine trust in AI’s capabilities and ensuring responsible innovation in domains where errors can have profound consequences.

Complex ML models often lack interpretability, hindering debugging and bias detection. Their opacity prevents validation of reasoning and understanding causal factors, problematic in critical applications. This lack of transparency is particularly problematic in high-stakes scenarios where understanding _why_ a decision was made is as crucial as the decision itself.

Opaque AI raises ethical concerns regarding fairness and bias. Explainability is crucial for ensuring accountability and building just AI systems that align with societal values. Explainability is therefore not merely a technical concern; it is a fundamental prerequisite for building AI systems that are just, equitable, and accountable. Understanding the lineage of a decision allows us to trace potential sources of bias, audit the model’s reasoning for fairness, and ultimately build AI that aligns with our ethical values.

Ontological AI offers a path to trustworthy and explainable systems by grounding reasoning in explicit, structured knowledge. This semantic foundation allows for tracing inferences back to defined concepts, enabling human-understandable explanations and greater reliability.

I will go deeper into how this foundational approach unlocks advanced explainability mechanisms and paves the way for more robust and reliable AI systems.

## A Toolkit for Reliability

Formal Verification of Ontologies: Ensuring the logical integrity of the foundational knowledge is paramount for reliable AI. This necessitates rigorous formal verification techniques. Leveraging Description Logics (DLs) like SHOIQ and OWL 2 DL allows for automated reasoning to detect inconsistencies, identify unsatisfiable concepts (e.g., a Human that is simultaneously not a Mammal), and uncover unintended logical consequences arising from the axiomatic structure. Reasoners such as HermiT, Pellet, and FaCT++ play a crucial role in performing these automated consistency checks and entailment analyses. For instance, consider a snippet in OWL 2:

```
<owl:Class rdf:about="#InconsistentConcept">    <owl:equivalentClass>        <owl:intersectionOf rdf:parseType="Collection">            <owl:Class rdf:about="#Mammal"/>            <owl:Class>                <owl:complementOf rdf:resource="#Mammal"/>            </owl:Class>        </owl:intersectionOf>    </owl:equivalentClass></owl:Class>
```

A DL reasoner would immediately flag _#InconsistentConcept_ as unsatisfiable, preventing its propagation into downstream AI reasoning. Furthermore, techniques like consequence-based reasoning can reveal non-obvious entailments, ensuring the ontology behaves as intended under logical scrutiny.

For complex domains, monolithic ontologies become unwieldy and difficult to maintain. Adopting a modular design paradigm is crucial for reusability, maintainability, and collaborative development. Principles such as high cohesion within modules and loose coupling between them are essential. Well-defined interfaces, specifying the vocabulary and intended semantics exchanged between modules, facilitate seamless integration. For example, a core ontology for `Medicine` might have separate modules for `Anatomy`, `Diseases`, and `Treatments`, each with clearly defined import relationships and articulation axioms to ensure semantic interoperability. This modularity allows different teams to work concurrently on specific knowledge areas without causing global inconsistencies and simplifies the process of updating or extending the knowledge base.

Integrating heterogeneous knowledge from diverse sources is a significant challenge in building comprehensive knowledge graphs for AI. Ontology alignment aims to find correspondences between entities and relations in different ontologies, while merging seeks to create a unified ontology. Approaches range from structural methods that analyze the hierarchical and relational structure to semantic techniques leveraging lexical similarities, distributional semantics, and logical reasoning. For instance, aligning a medical ontology using SNOMED CT with one using ICD-10 requires sophisticated techniques to map equivalent concepts (e.g., using cross-references or logical definitions). Resolving semantic conflicts arising from differing granularities or contradictory axioms after merging demands advanced strategies, such as employing provenance tracking, trust scores for different sources, and potentially using paraconsistent logics to handle inconsistencies gracefully. Ensuring coherence often involves defining articulation axioms that explicitly state the relationships between concepts from different ontologies within the merged schema.

## Addressing Vagueness with Ontologies

Traditional crisp ontologies, based on binary truth values, often struggle to represent the inherent uncertainty and vagueness present in real-world data. Fuzzy ontologies extend classical ontology formalisms by allowing for degrees of truth, typically represented by fuzzy sets and membership functions. For instance, the concept of “high blood pressure” isn’t a binary state but rather a spectrum. Integrating probabilistic models with ontological knowledge offers another powerful approach. Probabilistic Description Logics (PDLs) allow associating probabilities with axioms and concepts, enabling reasoning under uncertainty. Frameworks like Bayesian Networks can be overlaid on ontological structures to model probabilistic dependencies between concepts. Consider a scenario in medical diagnosis where the presence of a symptom only increases the probability of a specific disease. This can be represented by associating a conditional probability with the relationship between the symptom and the disease within the ontology. For example, in a PDL, we might have:

```
P(Disease(patient) = Diabetes | Symptom(patient) = FrequentUrination) = 0.8
```

This integration is particularly valuable in domains with noisy or incomplete data, allowing AI systems to provide more nuanced and probabilistic explanations rather than definitive, potentially incorrect ones.

The world is dynamic, and capturing the evolution of concepts and relationships over time is critical for many AI applications. Temporal ontologies extend standard ontologies to include temporal dimensions. This involves representing time points, time intervals, and temporal relations (e.g., before, after, during). Reasoning about past, present, and future states enables sophisticated event tracking, process modeling, and forecasting. For example, in a supply chain ontology, the relationship “isLocatedAt” between a Product and a Warehouse might have temporal qualifiers indicating the start and end times of the product’s storage. Formalisms like the Event Calculus or extensions of Description Logics with temporal operators (DL^T) provide the logical machinery to reason about temporal dependencies and consequences. Querying a temporal ontology could involve asking not just “where is product X?”, but “where was product X on date Y?”. This temporal awareness is crucial for providing accurate and contextually relevant explanations in dynamic environments.

The meaning of concepts and relationships is often context-dependent. Contextual ontologies aim to capture and represent these contextual nuances. This involves defining contexts explicitly and associating different interpretations or properties with concepts based on the active context. For instance, the term “bank” can refer to a financial institution or the side of a river, depending on the context of the discourse. Techniques for representing context range from using dedicated context entities and relations within the ontology to employing more sophisticated mechanisms like context-aware reasoning rules or viewpoint-based semantics. In natural language understanding, a contextual ontology can help disambiguate the meaning of terms in a query by considering the surrounding words and the overall topic. Similarly, in information retrieval, understanding the context of a document and a user’s query can lead to more relevant and semantically accurate results. Formalizing context allows AI systems to provide explanations that are sensitive to the specific situation, enhancing clarity and reducing ambiguity.

## The Role of Upper-Level Ontologies in Achieving Semantic Interoperability and Explainability

Upper-level ontologies, such as the Descriptive Ontology for Linguistic and Cognitive Engineering (DOLCE), the Suggested Upper Merged Ontology (SUMO), and the Basic Formal Ontology (BFO), serve as foundational frameworks by providing a minimal yet comprehensive set of highly abstract and domain-independent concepts and relations. These ontologies aim to capture fundamental distinctions, such as continuant vs. occurrent entities in BFO, or endurants vs. perdurants in DOLCE, along with core relations like parthood, causation, and instantiation. By offering a shared vocabulary and a consistent set of foundational principles, they provide a crucial semantic anchor for domain-specific ontologies. For instance, instead of defining “process” differently in manufacturing and healthcare ontologies, both can ground their respective notions in the `Process` concept of an upper-level ontology, inheriting its inherent properties and constraints.

The heterogeneity of knowledge sources and AI systems poses a significant barrier to seamless information exchange. Upper-level ontologies act as a semantic bridge, enabling different systems and knowledge bases to understand and interoperate more effectively. When domain ontologies are aligned with or grounded in a common upper-level ontology, the mappings between their respective concepts become more principled and semantically sound. Consider two knowledge graphs, one describing biological pathways and another detailing drug interactions. If both are rooted in BFO, the concept of a `BiologicalProcess` in the former and a `ChemicalProcess` in the latter can be understood as subtypes of the BFO `Process`, facilitating interoperability at a fundamental level. This shared understanding extends to relationships as well, allowing for more sophisticated data integration and knowledge sharing across disparate systems.

Grounding domain-specific knowledge in the well-defined categories and relations of an upper-level ontology can significantly enhance the transparency and intuitiveness of AI reasoning. When an AI system’s inference steps can be traced back to these foundational principles, the explanations become more robust and easier to comprehend, even for experts from different domains. For example, if an AI system diagnoses a disease based on a series of symptoms, and the relationships between these concepts and the disease are ultimately grounded in a causal relation defined in an upper-level ontology, the explanation can leverage this fundamental notion of causality, making the reasoning more transparent than a purely statistical correlation. Furthermore, the inherent constraints and axioms within the upper-level ontology can provide a logical backbone for the explanations, ensuring they are not only understandable but also logically sound.

Selecting an appropriate upper-level ontology requires careful consideration of its philosophical commitments, scope, and modularity. There are trade-offs between the broad coverage of SUMO, the cognitively motivated distinctions of DOLCE, and the scientifically grounded principles of BFO. Often, direct adoption is not feasible, and adaptation or extension of the chosen upper-level ontology to better suit the specific domain requirements becomes necessary. This might involve introducing new intermediate-level concepts or refining existing definitions while maintaining alignment with the foundational principles. Best practices include clearly documenting any modifications and ensuring that the adapted ontology remains logically consistent. Furthermore, the choice of an upper-level ontology can influence the expressivity and computational properties of the resulting knowledge base, impacting the feasibility of certain types of reasoning and explanation generation.

## Applications

### Product Recommendation in Banking with Ontological Grounding

In the realm of financial product recommendation, moving beyond simple collaborative filtering or content-based methods towards explainable AI is crucial for building trust and fostering user understanding of the recommendations. Ontological engineering allows for the explicit modeling of financial products (e.g., `SavingsAccount`, `CreditCard`, `Loan`, `InvestmentFund`), customer profiles (`Customer`), their financial goals (`FinancialGoal` like `RetirementPlanning`, `HomePurchase`), their financial situation (`FinancialSituation` including `Income`, `CreditScore`, `RiskAppetite`), and the relationships between these entities (e.g., `isSuitableForGoal`, `requiresIncomeLevel`, `hasRiskProfile`).

Consider a scenario where an AI system recommends a specific `InvestmentFund` to a `Customer`. Without an ontology, the explanation might be vague (e.g., "customers with similar profiles also invested in this fund"). However, with an ontology-driven approach, the explanation can be much more insightful and grounded in the user's specific needs and the product's characteristics:

“The `GrowthPlus Fund` is recommended for you, `Customer C789`, because it aligns with your stated `FinancialGoal:LongTermGrowth` and your identified `RiskAppetite:Moderate`. The `GrowthPlus Fund` (defined as an `InvestmentFund` with `investmentStrategy:GrowthOriented`) is ontologically linked to the goal of long-term growth through the `isSuitableForGoal` relationship, which is further specified by the axiom that funds with a 'growth-oriented' strategy are suitable for 'long-term growth' goals. Additionally, your moderate risk appetite (`hasRiskAppetite:Moderate`) is compatible with the fund's risk profile (`hasRiskProfile:Moderate`), as defined by the compatibility rule: 'A customer's risk appetite should be equal to or higher than the risk profile of the recommended investment product.' Furthermore, your current `FinancialSituation:StableIncome` meets the fund's requirement of at least a 'stable' income level (`requiresIncomeLevel:StableOrHigher`)."

## Get Chris Shayan’s stories in your inbox

Join Medium for free to get updates from this writer.

Here’s a conceptual representation of a relevant portion of such an ontology:

```
ex:Customer_C789 rdf:type ex:Customer ;    ex:hasFinancialGoal ex:Goal_LongTermGrowth ;    ex:hasRiskAppetite ex:RiskAppetite_Moderate ;    ex:hasFinancialSituation ex:Situation_StableIncome .ex:Goal_LongTermGrowth rdf:type ex:FinancialGoal ;    rdfs:label "Long-Term Growth" .ex:RiskAppetite_Moderate rdf:type ex:RiskAppetite ;    rdfs:label "Moderate" .ex:Situation_StableIncome rdf:type ex:FinancialSituation ;    rdfs:label "Stable Income" .ex:InvestmentFund_GrowthPlus rdf:type ex:InvestmentFund ;    rdfs:label "GrowthPlus Fund" ;    ex:hasInvestmentStrategy ex:Strategy_GrowthOriented ;    ex:hasRiskProfile ex:RiskProfile_Moderate ;    ex:requiresIncomeLevel ex:IncomeLevel_Stable .ex:Strategy_GrowthOriented rdf:type ex:InvestmentStrategy ;    rdfs:label "Growth-Oriented" .ex:RiskProfile_Moderate rdf:type ex:RiskProfile ;    rdfs:label "Moderate" .ex:IncomeLevel_Stable rdf:type ex:IncomeLevel ;    rdfs:label "Stable" .ex:isSuitableForGoal rdfs:domain ex:FinancialProduct ;    rdfs:range ex:FinancialGoal .ex:hasInvestmentStrategy rdfs:domain ex:InvestmentFund ;    rdfs:range ex:InvestmentStrategy .ex:hasRiskProfile rdfs:domain ex:FinancialProduct ;    rdfs:range ex:RiskProfile .ex:requiresIncomeLevel rdfs:domain ex:FinancialProduct ;    rdfs:range ex:IncomeLevel .ex:hasFinancialGoal rdfs:domain ex:Customer ;    rdfs:range ex:FinancialGoal .ex:hasRiskAppetite rdfs:domain ex:Customer ;    rdfs:range ex:RiskAppetite .ex:hasFinancialSituation rdfs:domain ex:Customer ;    rdfs:range ex:FinancialSituation .# Axiomatic knowledge:ex:GrowthOrientedStrategySuitableForLongTermGrowth    rdfs:subPropertyOf ex:isSuitableForGoal .    ex:GrowthOrientedStrategySuitableForLongTermGrowth rdfs:domain ex:InvestmentFund ;    rdfs:range ex:FinancialGoal .    owl:equivalentClass owl:intersectionOf (        [ owl:onProperty ex:hasInvestmentStrategy ; owl:hasValue ex:Strategy_GrowthOriented ]        [ owl:onProperty ex:isSuitableForGoal ; owl:hasValue ex:Goal_LongTermGrowth ]    ) .ex:CustomerRiskMatchesProductRisk    rdfs:subClassOf owl:Restriction .    owl:onProperty ex:hasRiskAppetite .    owl:allValuesFrom [ owl:unionOf (ex:RiskProfile_Moderate ex:RiskProfile_High) ] . # Simplified ruleex:ProductRequiresIncomeLevelStableOrHigher    rdfs:subClassOf owl:Restriction .    owl:onProperty ex:requiresIncomeLevel .    owl:allValuesFrom [ owl:unionOf (ex:IncomeLevel_Stable ex:IncomeLevel_High) ] . # Simplified rule
```

In this scenario, a reasoning engine would utilize the ontological relationships and axioms to determine the suitability of the `GrowthPlus Fund` for `Customer C789`. The explanation engine can then articulate the reasoning path, highlighting why the fund aligns with the customer's goals, risk appetite, and financial situation based on the explicit knowledge encoded in the ontology.

This ontological approach to product recommendation offers several advantages:

-   **Transparency:** The reasoning behind recommendations is explicit and traceable to defined concepts and relationships.
-   **Personalization:** Recommendations are based on a deeper understanding of the customer’s individual profile and goals.
-   **Trust Building:** Clear explanations enhance user trust in the recommendation system.
-   **Regulatory Compliance:** In finance, the ability to justify recommendations based on well-defined criteria can aid in meeting regulatory requirements.

By leveraging ontologies, financial platforms can move towards more transparent, personalized, and trustworthy product recommendation systems.

### Healthcare

In healthcare, ontologies like SNOMED CT and the Gene Ontology provide a structured vocabulary for diseases, symptoms, treatments, and biological processes. AI systems leveraging these ontologies for clinical decision support can offer explanations grounded in established medical knowledge. For example, a system recommending a particular treatment could explain its reasoning by referencing the ontological relationships between the patient’s symptoms, the diagnosed condition, and the known efficacy of the treatment for that condition, potentially citing specific biological pathways or mechanisms defined in the ontology.

### Supply Chain Management

Ontologies can model the complex network of entities and processes involved in a supply chain, including products, suppliers, locations, and transportation methods. For provenance tracking, an ontology can represent the origin and history of a product, along with the transformations it undergoes. An AI system using this ontology could explain the provenance of a specific item by tracing its path through the supply chain, referencing the “wasProcessedBy,” “wasTransportedTo,” and “originatedFrom” relationships defined in the ontology. This provides transparency regarding the product’s journey and can be crucial for quality control and regulatory compliance.

### Knowledge Management

Ontologies enhance enterprise search by providing a semantic layer over unstructured data. Instead of relying solely on keyword matching, an ontology-driven search can understand the meaning of terms and the relationships between concepts. Explanations for search results can then be based on the semantic relevance determined by the ontology. For instance, a search for “customer issues” might return not only documents containing those exact words but also documents related to “complaints” (a synonym defined in the ontology) or “support tickets” (a related concept), with the system explaining these semantic connections.

Ontologies are not standalone solutions for XAI but can be powerful components within broader explainable AI architectures. They can be integrated with other XAI techniques in several ways:

-   **Rule Extraction:** Ontologies can serve as the source of structured knowledge from which explicit rules for rule-based explainers can be derived. The ontological axioms and relationships can be translated into human-readable “if-then” rules.
-   **Attention Mechanisms:** In neural networks, ontological knowledge can be used to guide attention mechanisms, ensuring that the model focuses on semantically relevant parts of the input. The ontological relationships between entities in the input can inform the attention weights, and the explanations can then highlight these semantically important connections.
-   **Causal Reasoning:** Ontologies, particularly those modeling processes and dependencies, can provide a framework for causal reasoning. By grounding AI inferences in ontologically defined causal relationships, the explanations can go beyond correlation and provide insights into the underlying causal mechanisms.
-   **Knowledge Graph Embeddings:** While knowledge graph embeddings themselves can be opaque, the underlying ontology provides the semantic framework for interpreting these embeddings. Ontological constraints and relationships can be used to regularize the embedding space and to generate symbolic explanations based on the learned embeddings.

## Future Directions

The creation of robust ontologies is a major hurdle, demanding deep expertise and careful formalization. Scaling development for intricate domains requires significant time and resources. Progress in automated ontology construction, leveraging NLP and machine learning, is crucial. Ensuring logical consistency in large ontologies necessitates advanced verification and expressive languages.

Applying ontological reasoning to massive datasets poses substantial computational challenges. Traditional engines struggle with the scale and query complexity of large knowledge graphs. Future efforts focus on efficient storage, specialized databases, and approximate reasoning. Research into incremental reasoning is vital for handling dynamic big data in real-world applications.

A key trend is the fusion of symbolic (ontological) and sub-symbolic (machine learning) AI for enhanced explainability. Ontologies provide structure for machine learning, improving data and model interpretability. Conversely, machine learning can automate ontology engineering tasks like concept and relation extraction. Current research explores neurosymbolic systems and ontology-informed knowledge graph embeddings.

The field of ontological AI and its application to explainability is rapidly evolving, with several exciting emerging trends and open research questions:

-   **Causal Reasoning with Ontologies:** Extending ontologies to explicitly represent causal relationships and leveraging them for causal inference and explanation remains a key area of research.
-   **Explainable Knowledge Graph Embeddings:** Developing embedding techniques that not only capture the relational structure of knowledge graphs but also provide interpretable representations and facilitate symbolic explanation generation.
-   **Contextualized and Personalized Explanations:** Tailoring explanations to the specific user’s background knowledge, cognitive abilities, and the context of the query or decision.
-   **Trustworthy AI through Ontological Grounding:** Investigating how the explicit and verifiable nature of ontological knowledge can contribute to building more trustworthy and reliable AI systems.
-   **Formalizing Uncertainty and Vagueness in Explanations:** Developing methods to communicate the inherent uncertainty and vagueness present in the data and the reasoning process within the explanations themselves.
-   **Ontology-Driven Explainable Reinforcement Learning:** Using ontologies to structure the state and action spaces in reinforcement learning and to generate symbolic explanations for the agent’s behavior.
-   **Standardization and Interoperability of XAI Frameworks based on Ontologies:** Developing common standards and methodologies for building ontology-driven explainable AI systems to facilitate interoperability and reproducibility.

Addressing these challenges and exploring these future directions will be crucial for unlocking the full potential of ontologies in driving the next generation of truly explainable and trustworthy artificial intelligence systems.
