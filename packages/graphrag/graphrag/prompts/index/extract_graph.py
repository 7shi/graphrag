# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""A file containing prompts definition."""

GRAPH_EXTRACTION_PROMPT = """
-Goal-
Given a text document that is potentially relevant to this activity and a list of entity types, identify all entities of those types from the text and all relationships among the identified entities.

-Steps-
1. Identify all entities. For each identified entity, extract the following information:
- name: Name of the entity, capitalized
- type: One of the following types: [{entity_types}]
- description: Comprehensive description of the entity's attributes and activities

2. From the entities identified in step 1, identify all pairs of (source, target) that are *clearly related* to each other.
For each pair of related entities, extract the following information:
- source: name of the source entity, as identified in step 1
- target: name of the target entity, as identified in step 1
- description: explanation as to why you think the source entity and the target entity are related to each other
- strength: a numeric score indicating strength of the relationship between the source entity and target entity

3. Return the result as a single JSON object with two keys, "entities" and "relationships", each holding a list of the items identified in steps 1 and 2. Use this exact shape:
{"entities": [{"name": "...", "type": "...", "description": "..."}], "relationships": [{"source": "...", "target": "...", "description": "...", "strength": 1}]}

######################
-Examples-
######################
Example 1:
Entity_types: ORGANIZATION,PERSON
Text:
The Verdantis's Central Institution is scheduled to meet on Monday and Thursday, with the institution planning to release its latest policy decision on Thursday at 1:30 p.m. PDT, followed by a press conference where Central Institution Chair Martin Smith will take questions. Investors expect the Market Strategy Committee to hold its benchmark interest rate steady in a range of 3.5%-3.75%.
######################
Output:
{"entities": [{"name": "CENTRAL INSTITUTION", "type": "ORGANIZATION", "description": "The Central Institution is the Federal Reserve of Verdantis, which is setting interest rates on Monday and Thursday"}, {"name": "MARTIN SMITH", "type": "PERSON", "description": "Martin Smith is the chair of the Central Institution"}, {"name": "MARKET STRATEGY COMMITTEE", "type": "ORGANIZATION", "description": "The Central Institution committee makes key decisions about interest rates and the growth of Verdantis's money supply"}], "relationships": [{"source": "MARTIN SMITH", "target": "CENTRAL INSTITUTION", "description": "Martin Smith is the Chair of the Central Institution and will answer questions at a press conference", "strength": 9}]}

######################
Example 2:
Entity_types: ORGANIZATION
Text:
TechGlobal's (TG) stock skyrocketed in its opening day on the Global Exchange Thursday. But IPO experts warn that the semiconductor corporation's debut on the public markets isn't indicative of how other newly listed companies may perform.

TechGlobal, a formerly public company, was taken private by Vision Holdings in 2014. The well-established chip designer says it powers 85% of premium smartphones.
######################
Output:
{"entities": [{"name": "TECHGLOBAL", "type": "ORGANIZATION", "description": "TechGlobal is a stock now listed on the Global Exchange which powers 85% of premium smartphones"}, {"name": "VISION HOLDINGS", "type": "ORGANIZATION", "description": "Vision Holdings is a firm that previously owned TechGlobal"}], "relationships": [{"source": "TECHGLOBAL", "target": "VISION HOLDINGS", "description": "Vision Holdings formerly owned TechGlobal from 2014 until present", "strength": 5}]}

######################
Example 3:
Entity_types: ORGANIZATION,GEO,PERSON
Text:
Five Aurelians jailed for 8 years in Firuzabad and widely regarded as hostages are on their way home to Aurelia.

The swap orchestrated by Quintara was finalized when $8bn of Firuzi funds were transferred to financial institutions in Krohaara, the capital of Quintara.

The exchange initiated in Firuzabad's capital, Tiruzia, led to the four men and one woman, who are also Firuzi nationals, boarding a chartered flight to Krohaara.

They were welcomed by senior Aurelian officials and are now on their way to Aurelia's capital, Cashion.

The Aurelians include 39-year-old businessman Samuel Namara, who has been held in Tiruzia's Alhamia Prison, as well as journalist Durke Bataglani, 59, and environmentalist Meggie Tazbah, 53, who also holds Bratinas nationality.
######################
Output:
{"entities": [{"name": "FIRUZABAD", "type": "GEO", "description": "Firuzabad held Aurelians as hostages"}, {"name": "AURELIA", "type": "GEO", "description": "Country seeking to release hostages"}, {"name": "QUINTARA", "type": "GEO", "description": "Country that negotiated a swap of money in exchange for hostages"}, {"name": "TIRUZIA", "type": "GEO", "description": "Capital of Firuzabad where the Aurelians were being held"}, {"name": "KROHAARA", "type": "GEO", "description": "Capital city in Quintara"}, {"name": "CASHION", "type": "GEO", "description": "Capital city in Aurelia"}, {"name": "SAMUEL NAMARA", "type": "PERSON", "description": "Aurelian who spent time in Tiruzia's Alhamia Prison"}, {"name": "ALHAMIA PRISON", "type": "GEO", "description": "Prison in Tiruzia"}, {"name": "DURKE BATAGLANI", "type": "PERSON", "description": "Aurelian journalist who was held hostage"}, {"name": "MEGGIE TAZBAH", "type": "PERSON", "description": "Bratinas national and environmentalist who was held hostage"}], "relationships": [{"source": "FIRUZABAD", "target": "AURELIA", "description": "Firuzabad negotiated a hostage exchange with Aurelia", "strength": 2}, {"source": "QUINTARA", "target": "AURELIA", "description": "Quintara brokered the hostage exchange between Firuzabad and Aurelia", "strength": 2}, {"source": "QUINTARA", "target": "FIRUZABAD", "description": "Quintara brokered the hostage exchange between Firuzabad and Aurelia", "strength": 2}, {"source": "SAMUEL NAMARA", "target": "ALHAMIA PRISON", "description": "Samuel Namara was a prisoner at Alhamia prison", "strength": 8}, {"source": "SAMUEL NAMARA", "target": "MEGGIE TAZBAH", "description": "Samuel Namara and Meggie Tazbah were exchanged in the same hostage release", "strength": 2}, {"source": "SAMUEL NAMARA", "target": "DURKE BATAGLANI", "description": "Samuel Namara and Durke Bataglani were exchanged in the same hostage release", "strength": 2}, {"source": "MEGGIE TAZBAH", "target": "DURKE BATAGLANI", "description": "Meggie Tazbah and Durke Bataglani were exchanged in the same hostage release", "strength": 2}, {"source": "SAMUEL NAMARA", "target": "FIRUZABAD", "description": "Samuel Namara was a hostage in Firuzabad", "strength": 2}, {"source": "MEGGIE TAZBAH", "target": "FIRUZABAD", "description": "Meggie Tazbah was a hostage in Firuzabad", "strength": 2}, {"source": "DURKE BATAGLANI", "target": "FIRUZABAD", "description": "Durke Bataglani was a hostage in Firuzabad", "strength": 2}]}

######################
-Real Data-
######################
Entity_types: {entity_types}
Text: {input_text}
######################
Output:"""

CONTINUE_PROMPT = "MANY entities and relationships were missed in the last extraction. Remember to ONLY emit entities that match any of the previously extracted types. Add them below using the same JSON format (a single object with \"entities\" and \"relationships\" lists):\n"
LOOP_PROMPT = "It appears some entities and relationships may have still been missed. Answer Y if there are still entities or relationships that need to be added, or N if there are none. Please answer with a single letter Y or N.\n"
