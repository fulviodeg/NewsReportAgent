# Diagrammi architetturali

> Generato da LikeC4 (`docs/architecture/*.c4`) con `npm run docs:mermaid`. Non modificare a mano.
> Versione interattiva: https://fulviodeg.github.io/NewsReportAgent/

## Contesto (System Context)

```mermaid
---
title: "Contesto — News Report Agent"
---
graph TB
  Reader[fa:fa-user Lettore]
  Github[GitHub]
  Nra[News Report Agent]
  Mailbox[Mailbox dedicata]
  Openrouter[OpenRouter]
  Reader -. "apre nel browser (basic auth)" .-> Nra
  Nra -. "poll IMAP dei nuovi messaggi" .-> Mailbox
  Nra -. "classify + synthesize + embeddings" .-> Openrouter
  Github -. "GitHub Pages serve i diagrammi" .-> Nra
```

## Container

```mermaid
---
title: "Container"
---
graph TB
  Reader[fa:fa-user Lettore]
  Github[GitHub]
  subgraph Nra["News Report Agent"]
    Nra.Web[Dashboard]
    Nra.Pipeline[Pipeline]
    Nra.Store[Store]
  end
  Mailbox[Mailbox dedicata]
  Openrouter[OpenRouter]
  Reader -. "apre nel browser (basic auth)" .-> Nra.Web
  Github -. "GitHub Pages serve i diagrammi" .-> Nra.Web
  Nra.Pipeline -. "scrive item, cluster, JSON" .-> Nra.Store
  Nra.Web -. "legge export.json / archive.json" .-> Nra.Store
  Nra.Pipeline -. "poll IMAP dei nuovi messaggi" .-> Mailbox
  Nra.Pipeline -. "classify + synthesize + embeddings" .-> Openrouter
```

## Componenti della Pipeline

```mermaid
---
title: "Componenti della Pipeline"
---
graph TB
  subgraph NraPipeline["Pipeline"]
    NraPipeline.Config[Config]
    NraPipeline.Scheduler[Scheduler]
    NraPipeline.Ingest[Ingest]
    NraPipeline.Cluster[Cluster]
    NraPipeline.Parse[Parse]
    NraPipeline.Embeddings[Embeddings]
    NraPipeline.Classify[Classify]
    NraPipeline.Synthesize[Synthesize]
    NraPipeline.Llm[LLM client]
    NraPipeline.Export[Export]
    NraPipeline.Db[Store access]
  end
  NraPipeline.Config -. "cadenze, soglie, model" .-> NraPipeline.Scheduler
  NraPipeline.Scheduler -. "collection clock" .-> NraPipeline.Ingest
  NraPipeline.Scheduler -. "processing clock" .-> NraPipeline.Cluster
  NraPipeline.Ingest -. "messaggi grezzi" .-> NraPipeline.Parse
  NraPipeline.Parse -. "salva item" .-> NraPipeline.Db
  NraPipeline.Cluster -. "embed nuovi item" .-> NraPipeline.Embeddings
  NraPipeline.Cluster -. "cluster" .-> NraPipeline.Classify
  NraPipeline.Cluster -. "legge item, scrive cluster" .-> NraPipeline.Db
  NraPipeline.Classify -. "chat completion" .-> NraPipeline.Llm
  NraPipeline.Synthesize -. "chat completion" .-> NraPipeline.Llm
  NraPipeline.Classify -. "cluster classificato" .-> NraPipeline.Synthesize
  NraPipeline.Synthesize -. "storie pronte" .-> NraPipeline.Export
  NraPipeline.Export -. "legge storie" .-> NraPipeline.Db
```

## Dynamic — Collection clock

```mermaid
---
title: "Collection clock (frequente, senza LLM)"
---
graph LR
  NraPipelineScheduler[Scheduler]
  NraPipelineIngest[Ingest]
  NraPipelineParse[Parse]
  NraPipelineDb[Store access]
  NraPipelineScheduler -. "ogni N minuti (config)" .-> NraPipelineIngest
  NraPipelineIngest -. "messaggi grezzi" .-> NraPipelineParse
  NraPipelineParse -. "item (dedup per content hash)" .-> NraPipelineDb
```

## Dynamic — Processing clock

```mermaid
---
title: "Processing clock (LLM) + on-demand"
---
graph LR
  NraPipelineScheduler[Scheduler]
  NraPipelineCluster[Cluster]
  NraPipelineEmbeddings[Embeddings]
  NraPipelineDb[Store access]
  NraPipelineClassify[Classify]
  NraPipelineLlm[LLM client]
  NraPipelineSynthesize[Synthesize]
  NraPipelineExport[Export]
  NraStore[Store]
  NraPipelineScheduler -. "ogni N ore / on-demand" .-> NraPipelineCluster
  NraPipelineCluster -. "embed nuovi item" .-> NraPipelineEmbeddings
  NraPipelineCluster -. "crea cluster" .-> NraPipelineDb
  NraPipelineCluster -. "per cluster" .-> NraPipelineClassify
  NraPipelineClassify -. "tema, aziende, relevance" .-> NraPipelineLlm
  NraPipelineClassify -. "cluster classificato" .-> NraPipelineSynthesize
  NraPipelineSynthesize -. "sintesi IT + entities" .-> NraPipelineLlm
  NraPipelineSynthesize -. "storie pronte" .-> NraPipelineExport
  NraPipelineExport -. "export.json + archive.json (atomico)" .-> NraStore
```
