**Ask Your Data Case**

# **1\. What Is Collibra?**

Collibra is the leading **Data Intelligence platform**, recognized as a Leader by Gartner, Forrester, and IDC. Founded in 2008, Collibra provides a unified platform to govern data and AI, giving organizations the visibility, control, and confidence to turn data into a trusted strategic asset.

Large enterprises (banks, insurers, pharmaceutical companies, tech firms, public institutions) sit on enormous volumes of data spread across dozens of systems. The challenge is not having data. It is making that data findable, understandable, trustworthy, and usable. Collibra solves this by connecting three things that are usually disconnected in large organizations:

* **The technical data** living in databases, warehouses, and lakes.

* **The business context** (definitions, policies, metrics, ownership) that gives that data meaning.

* **The people** who need to use it, from data engineers to business analysts to compliance officers.

The platform covers a broad range of capabilities. Here are a few examples:

* **Business Glossary.** The system where an organization governs its business terms, definitions, and metrics, enabling everyone to understand data assets from a business perspective.

* **Data Catalog.** Delivers end-to-end visibility across data sources, allowing users to discover, describe, and understand data sets across the enterprise.

* **Data Quality.** Rules and checks that ensure data meets business standards, including adaptive rules, custom rules, and profiling.

* **Data Notebook.** Query data sources and share insights directly within Collibra using notebook-style assets.

* **Access Control.** A control tower that gives you tools to control access to your data landscape.

* **AI Governance.** Define, measure, and monitor AI use cases across the enterprise to maximize results while minimizing risks.

At its core, Collibra acts as the **Context and Control Engine** for the modern data stack: the single place where an organization documents what its data means, who owns it, how it should be used, and whether it can be trusted.

Context (the business meaning behind data) has been Collibra's bread and butter for over 15 years. That expertise has become more critical than ever in the age of AI.

# **2\. The Preview Program: How Collibra Builds With Customers**

Building enterprise software means solving problems that are genuinely complex, not just technically, but in how different organizations understand and use their data.

That is one of the reasons Collibra runs [preview programs](https://next.collibra.com/asset/0198c234-11fe-73ff-be9b-c9131285004f), structured pre-release phases where real customers get early access to upcoming features. These [programs](https://next.collibra.com/asset/485cd852-73cd-4d56-bb5c-bcef60b3cc37) serve two purposes:

**1\. Validate future releases.** Before anything ships to GA (General Availability), Collibra tests it with real users in real environments to catch issues and confirm the feature actually solves the problem it was designed for.

**2\. Get early feedback to build better products.** It is always easier to build something meaningful when you are working directly with the people who will use it, rather than building in isolation and hoping it lands.

## **The stages**

[Alpha (Internal Preview)](https://next.collibra.com/asset/1cad7f11-01d4-4475-afab-15ac0d4e0dc2)**.** The feature is tested internally by Collibra employees only. The goal is to validate the core experience and catch obvious issues before any customer sees it.

[Private Preview](https://next.collibra.com/asset/6ccf3d44-42a7-41e0-be74-b7f85bf922e5)**.** A selected group of external customers gets access. They commit to testing the feature, completing guided activities, submitting feedback (issues, ideas, or praise), filling in surveys, and engaging directly with the Product team. This is the most intensive validation stage and is managed through [Centercode](https://next.collibra.com/asset/0198c234-11fe-73ff-be9b-c91312850034), a dedicated platform for running and tracking beta programs.

[Public Preview](https://next.collibra.com/asset/0198c234-11fe-73ff-be9b-c91312850052)**.** The feature becomes available to all customers behind a customer-controlled toggle. Feedback comes through broader channels. The feature is close to final but not yet fully released.

## **Why this matters for the hackathon**

**The dataset you will work with comes directly from these preview programs.** It is real operational data that Collibra's Product and Customer Validation teams use every week. The questions you will be asked to answer are the questions they actually ask.

# **3\. The Problem: AI Without Context Is Just Guessing**

Business users no longer want to wait three days for a report. They want to open a chat interface, ask a question in plain English, and get an answer they can act on. The tools to do this exist today. You can connect any large language model to a data warehouse in one hour. Give it access to the tables, ask a question, it generates a SQL query, it returns a number.

It looks like it works. The problem is that it is very often **wrong**, and the answer looks exactly the same whether it is right or wrong.

## **A concrete example**

**Question:** "How many [active testers](https://next.collibra.com/asset/0198c234-11fe-73ff-be9b-c91312850031) do we have in the ongoing programs?"

Sounds simple. Just count the users where the program status is "ongoing," right?

Except: what is an "ongoing" program? Is it any program not marked as closed? Any program within its scheduled date range? Any program with recent activity?

And what is an "active" tester? Someone who logged in? Someone who submitted feedback? Someone who completed a certain number of activities?

The correct answer, the one Collibra's team actually uses, might be something like:

*A tester is active if they completed at least half of the assigned test activities, OR submitted at least two program surveys, OR logged at least three feedback tickets.*

None of that is in the database schema. It is a [business term](https://next.collibra.com/assettype/00000000-0000-0000-0000-000000011001/characteristics/4836452d-556b-48a4-a304-5a5a9118dce9). And without it, any answer the AI produces is a guess.

## **This is the norm, not the exception**

Now imagine you are not dealing with one table and one definition. You are dealing with petabytes of data across multiple warehouses, used by thousands of people across finance, operations, product, compliance, and sales. Every team has its own terminology. Every metric has its own nuance. Every KPI was defined in a meeting years ago and never written down anywhere a machine can find it. Most of the time, metrics are just lost in a piece of code somewhere on GitHub. Sometimes they live inside BI tools like Tableau, and good luck finding how a metric is actually defined in there. And that is just the calculations. The definitions themselves? Non-existent, or at best, living in a spreadsheet on somebody's laptop.

The AI does not know any of this. So it guesses. And the people reading the answer have no way of knowing whether the number is right or wrong, because it arrives with the same confidence either way.

This is not a model problem. The model is doing exactly what it was asked to do. **It is a context problem.** The model was never given the information it needed to answer correctly.

# **4\. The Challenge: Build "Ask Your Data Product"**

## **What you are building**

Build a prototype called **"Ask Your Data Product"**: a system where a business user can ask a plain-language question about Collibra's preview program data and receive a **trustworthy, governed answer**.

## **What we give you**

| Resource | Description |
| :---- | :---- |
| **Dataset in Databricks** | Real operational data from Collibra's preview programs: participants, activities, feedback, survey scores |
| **Collibra instance** | A populated instance with business glossary, definitions, metrics, and semantic relationships. Accessible via the UI, CSV export, or the API |
| **SQL notebook** | Prior analysis with questions and verified answers. Use this both as context and to validate your system |
| **Sample Code** | API examples for retrieving context from Collibra. These are building blocks to get you started, not the solution itself.  |

## **What context actually means**

Context is not one thing. In the resources we provide, it takes many forms:

* Business term definitions (e.g., what "active tester" means)

* Metric calculations (e.g., how a satisfaction score is computed)

* Table and column descriptions (e.g., what each field in the dataset represents)

* Pre-written SQL queries (e.g., the notebook with questions and verified answers)

* Semantic relationships (e.g., which business terms map to which data assets)

It can be anything that helps an AI reason correctly about the data. How you shape it, combine it, and feed it to the model to reliably answer business questions: **that is what will set your solution apart.**

## **What your prototype must do**

**1\. Retrieve context before answering.** Before answering any question, your system must consult the semantic context to understand what the question is actually asking. What does the key term mean? How is the relevant metric defined?

**2\. Bridge to the data.** Use that semantic context to translate the natural-language question into an accurate, executable query against the underlying dataset. The answer must come from the data, informed by the definition.

**3\. Handle the gap.** Not every term will be governed, and that's expected. When a user asks about something that doesn't yet have an asset or definition in Collibra, flagging the absence of a governed definition is just as valuable as using one when it exists. Knowing what *isn't* defined is itself a form of data intelligence.

## **What we expect**

* **Deterministic answers.** Given the same question, the system should produce the same answer based on the semantic context. We want to see the sources used by your system producing the output. 

* **Transparent reasoning.** We should be able to see the logic behind the answer: the SQL code (or whatever query language you choose), the definitions used, the chain from question to result.

* **Verifiable accuracy.** Ask the same questions that appear in the SQL notebook. Your answers should match. If we ask for the definition of a participant, the system must use the [definition](https://next.collibra.com/asset/019c9e6f-c4dc-711e-a8fb-b8d330b09cab) in Collibra.

# **5\. The Demo and the Pitch**

## **The before-and-after**

The core of your demo should make the difference impossible to ignore.

**Without context.** Just plug the LLM into the warehouse. No definitions, no glossary, no semantic layer. Ask it a question. Watch it pick a column, count some rows, and return a confident number that may be completely wrong.

**With context.** Your system retrieves the governed definition from Collibra, understands the exact criteria, constructs the right query, and returns a number you can trust.

Show this side by side. That contrast is the heart of your pitch.

## **What you will deliver**

1. A **working prototype** that answers business questions using governed context.

2. A **before-and-after demo** showing the difference between guessing and knowing.

3. A **pitch**: can we take real business decisions based on the output of your system? How do we trust it? 

# **Are You Ready?**

At Collibra, you will not just be coding. You will be solving the single biggest challenge in the AI revolution: **trust**.

We are looking for the next generation of engineers and entrepreneurs who want to prove, in 24 hours, that governed data is the difference between an AI that guesses and one that knows.

**Are you ready to build the brain that makes AI smart?**