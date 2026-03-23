# RelayPackage & New Repository Specification (Phase 0 Frozen Protocol)

> Version: v1  
> Status: Frozen Protocol for Phase 0  
> Scope: Repository structure, RelayPackage structure, INDEX / Delete formats, picture naming, merge chunking, validation rules, component boundaries

---

## 1. Purpose

This specification defines the frozen protocol for the new repository system and RelayPackage workflow.

It is the shared baseline for:

- the formal data repository
- RelayPackage
- RelayPackage Refresh Component
- Data_Merge_Tool
- frontend layer management / workflow export logic

The objective is to standardize:

- feature **create / overwrite / delete**
- feature-picture binding by **ID**
- package-based handoff, validation, repository update, and merge rebuild

---

## 2. Core Semantics

### 2.1 Feature States

Only three operation states exist in the system:

- **Create**
- **Overwrite**
- **Delete**

Definitions:

- a newly introduced feature JSON = **Create**
- an existing feature JSON being replaced = **Overwrite**
- an existing feature's picture set being replaced, expanded, or reordered = **Overwrite**
- removing an existing feature ID from the system = **Delete**

---

### 2.2 Picture Semantics

Pictures are not treated as independent business objects.

A picture is always treated as:

**an attached resource belonging to one feature ID**

Therefore:

- picture update is not a fourth operation type
- all picture updates are part of feature **Overwrite**

---

### 2.3 Primary Key

The unique primary key of a feature is:

- **ID**

The binding between feature and picture depends only on:

- **ID**

---

## 3. Formal Repository Structure

### 3.1 Top-Level Repository Structure

```text
/Data_Spilt
/Data_Merge
/Picture
/Data_Merge_Tool
```

This top-level structure is frozen for the formal repository.

---

### 3.2 Data_Spilt

#### Purpose
- source data layer
- manually maintainable layer
- one-feature-per-file storage

#### Directory Rules
- normal classes: `world/class/id.json`
- special classes (`ISG / ISL / ISP`): `world/class/kind/id.json`

#### Example
```text
Data_Spilt/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001.json
    ISG/
      station/
        INDEX.json
        ISG_0001.json
```

---

### 3.3 Data_Merge

#### Purpose
- runtime reading layer for the website
- chunked storage layer
- tool-generated layer

#### Directory Rules
- structure mirrors `Data_Spilt`
- data files are fixed-length chunks: `chunk_xxx.json`

#### Example
```text
Data_Merge/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      chunk_001.json
      chunk_002.json
    ISG/
      station/
        INDEX.json
        chunk_001.json
```

#### Mandatory Rule
- `Data_Merge` must not be manually edited
- `Data_Merge` may only be rebuilt by the formal Tool

---

### 3.4 Picture

#### Purpose
- attached picture resource layer for features

#### Directory Rules
- mirrors the same hierarchy as `Data_Spilt`
- picture folder name = feature ID
- picture filename = `ID_n.ext`

#### Example
```text
Picture/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001/
        RLE_0001_1.jpg
        RLE_0001_2.jpg
    ISG/
      station/
        INDEX.json
        ISG_0001/
          ISG_0001_1.png
```

---

## 4. RelayPackage Structure

### 4.1 RelayPackage Top-Level Structure

```text
RelayPackage/
  INDEX.json
  Delete.json
  Data_Spilt/
  Picture/
```

#### Mandatory Rules
- RelayPackage must not include `Data_Merge`
- RelayPackage only carries incremental content
- RelayPackage may be manually edited, but final validity is determined by Refresh Component / Tool validation

---

### 4.2 RelayPackage Semantics

- `Data_Spilt/`: feature JSONs for **Create** or **Overwrite**
- `Picture/`: picture files for **Create** or **Overwrite**
- `Delete.json`: feature IDs to be deleted
- `INDEX.json`: package summary and metadata

---

## 5. INDEX Specifications

### 5.1 Data_Spilt Category INDEX

#### Applies To
- `Data_Spilt/{world}/{class}/INDEX.json`
- `Data_Spilt/{world}/{class}/{kind}/INDEX.json`

#### Fixed Fields
```json
{
  "version": 12,
  "itemCount": 358,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002",
    "RLE_0003"
  ]
}
```

#### Field Definitions
- `version`: category directory version number
- `itemCount`: total feature count in the directory
- `updatedAt`: last update timestamp
- `items`: full feature ID list in the directory

---

### 5.2 Data_Merge Category INDEX

#### Applies To
- `Data_Merge/{world}/{class}/INDEX.json`
- `Data_Merge/{world}/{class}/{kind}/INDEX.json`

#### Fixed Fields
```json
{
  "version": 12,
  "itemCount": 358,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002"
  ],
  "chunkSize": 200,
  "chunkCount": 2,
  "chunks": [
    {
      "file": "chunk_001.json",
      "itemCount": 200,
      "items": [
        "RLE_0001",
        "RLE_0002"
      ]
    },
    {
      "file": "chunk_002.json",
      "itemCount": 158,
      "items": [
        "RLE_0201",
        "RLE_0202"
      ]
    }
  ]
}
```

#### Field Definitions
- `version`
- `itemCount`
- `updatedAt`
- `items`
- `chunkSize`
- `chunkCount`
- `chunks`

Each entry in `chunks` must include:
- `file`
- `itemCount`
- `items`

---

### 5.3 Data_Spilt / Data_Merge Root INDEX

#### Applies To
- `Data_Spilt/INDEX.json`
- `Data_Merge/INDEX.json`

#### Fixed Fields
```json
{
  "version": 7,
  "updatedAt": "2026-03-21T15:42:00+08:00"
}
```

#### Field Definitions
- `version`
- `updatedAt`

The root INDEX does not carry detailed lists.

---

### 5.4 Picture Category INDEX

#### Applies To
- `Picture/{world}/{class}/INDEX.json`
- `Picture/{world}/{class}/{kind}/INDEX.json`

#### Fixed Fields
```json
{
  "version": 12,
  "itemCount": 120,
  "updatedAt": "2026-03-21T15:42:00+08:00",
  "mapping": {
    "RLE_0001": [
      "RLE_0001/RLE_0001_1.jpg",
      "RLE_0001/RLE_0001_2.jpg"
    ],
    "RLE_0002": [
      "RLE_0002/RLE_0002_1.png"
    ]
  }
}
```

#### Field Definitions
- `version`
- `itemCount`
- `updatedAt`
- `mapping`

Where:
- `itemCount` = number of feature IDs with picture records
- `mapping` = `ID -> relative picture path list`

---

### 5.5 Picture Root INDEX

#### Applies To
- `Picture/INDEX.json`

#### Fixed Fields
```json
{
  "version": 7,
  "updatedAt": "2026-03-21T15:42:00+08:00"
}
```

---

### 5.6 RelayPackage INDEX

#### Fixed Fields
```json
{
  "version": 1,
  "packageId": "PKG_20260321_1542_001",
  "createdAt": "2026-03-21T15:42:00+08:00",
  "operator": "Yiqi Zhu",
  "splitFileCount": 12,
  "pictureFileCount": 27,
  "deleteCount": 3,
  "toolVersion": "1.0",
  "note": "zth RLE and STA update"
}
```

#### Field Definitions
- `version`
- `packageId`
- `createdAt`
- `operator`
- `splitFileCount`
- `pictureFileCount`
- `deleteCount`
- `toolVersion`
- `note`

Notes:
- `note` is optional
- all other fields are recommended as required

---

## 6. Delete Specification

### 6.1 Fixed Fields
```json
{
  "markedAt": "2026-03-21T15:42:00+08:00",
  "items": [
    "RLE_0001",
    "RLE_0002",
    "STA_0103"
  ]
}
```

### 6.2 Field Definitions
- `markedAt`: timestamp when delete marks were generated
- `items`: feature ID list to be deleted

### 6.3 Delete Semantics
When the formal Tool executes deletion, it must:

1. delete the corresponding JSON from `Data_Spilt`
2. delete the corresponding ID picture directory from `Picture`
3. rebuild affected `Data_Merge`
4. update affected `INDEX` files

Delete strategy is frozen as:

- **physical delete**

---

## 7. Picture Naming Rules

### 7.1 Folder Naming
Picture directory name must be:

- `ID`

Example:
```text
RLE_0001/
```

### 7.2 File Naming
Picture filename must be:

- `ID_n.ext`

Example:
```text
RLE_0001_1.jpg
RLE_0001_2.jpg
```

### 7.3 Frozen Rules
- no cover-picture concept
- picture order depends entirely on `_n`
- frontend upload must auto-rename pictures
- Tool / Refresh Component validate against this rule

---

## 8. Merge Chunking Rules

### 8.1 Chunk Strategy
- chunk size is a **fixed global value**
- v1 does not support class-specific chunk sizes
- v1 does not support direct in-chunk partial editing
- v1 rebuilds `Data_Merge` at the **affected directory level**

### 8.2 Chunk Filename
Chunk files must use:

```text
chunk_001.json
chunk_002.json
```

### 8.3 Chunk Metadata
`Data_Merge/INDEX.json` must record:
- `chunkSize`
- `chunkCount`
- `chunks[].file`
- `chunks[].itemCount`
- `chunks[].items`

---

## 9. Time, Ordering, and Version Rules

### 9.1 Time Format
All timestamps must use:

- **ISO 8601**
- **UTC+8**
- preferably minute- or second-level precision
- recommended format: `2026-03-21T15:42:00+08:00`

Applies to:
- `updatedAt`
- `createdAt`
- `markedAt`

---

### 9.2 Stable Ordering
The following `items` lists should be written in stable ascending string order:

- `Data_Spilt INDEX.items`
- `Data_Merge INDEX.items`
- `Data_Merge INDEX.chunks[].items`
- `Delete.json.items`

Frozen principle:
- Tool output must be stable
- Refresh Component output must be stable

---

### 9.3 Version Rules
- each successful Tool write to an affected category directory increments that directory `version` by 1
- each successful Tool write to a root directory increments the root `version` by 1
- Refresh Component rebuild does not change the schema meaning of `RelayPackage/INDEX.json.version`
- `RelayPackage/INDEX.json.version` means **schema version**, not package content revision number

---

## 10. RelayPackage Refresh Component

### 10.1 Position
The Refresh Component only handles:

- **the current RelayPackage itself**

It must not directly modify the formal repository.

---

### 10.2 Responsibilities
The Refresh Component must:

1. scan current package content
2. rebuild package-level `INDEX.json`
3. perform package-internal precheck
4. output a human-readable report
5. optionally repack to zip

---

### 10.3 Input
- current RelayPackage directory

### 10.4 Output
- updated `RelayPackage/INDEX.json`
- `check_report.md`
- optional `check_report.json`
- optional zip package

### 10.5 Deployment Principle
Frozen as:
- externally maintained unified program
- package may contain only a launcher entry
- do not copy the full formal executable into every package

---

## 11. Formal Tool Boundary

### 11.1 The Formal Tool Is Responsible For
1. reading a package
2. precheck
3. applying create / overwrite
4. executing delete
5. rebuilding merge
6. updating INDEX files
7. outputting formal reports

### 11.2 The Formal Tool Is Not Responsible For
- frontend cache management
- manual editing UI logic
- website UI rendering
- picture ordering UI interaction inside a package

---

## 12. Validation and Conflict Detection

### 12.1 Problem Levels
Precheck problems are frozen into two levels:

- **Blocking**
- **Warning**

---

### 12.2 Blocking Problems
These must stop direct application by default:

- invalid JSON
- invalid directory hierarchy
- filename does not match internal ID
- picture filename does not follow `ID_n`
- unresolvable same-ID conflict inside one package
- required package files missing

---

### 12.3 Warning Problems
These may be reported while still allowing continuation:

- non-continuous picture numbering
- overwrite existing feature
- overwrite existing pictures
- delete target does not exist
- empty picture directory
- package INDEX inconsistent with actual files but rebuildable

---

### 12.4 Report Format
The frozen human-readable main report is:

- `check_report.md`

Optional additional output:
- `check_report.json`

---

## 13. Frontend Export Boundary

### 13.1 Frontend Responsibilities
The frontend layer management / workflow side must later support:

- local cache for create / overwrite JSON
- local picture cache
- automatic picture rename to `ID_n.ext`
- delete-mark list maintenance
- automatic RelayPackage export
- automatic `RelayPackage/INDEX.json` generation
- automatic `Delete.json` generation

### 13.2 Frontend Must Not Directly Handle
- formal repository write
- formal merge rebuild
- formal INDEX rebuild

These are frozen as Tool-side responsibilities.

---

## 14. Completion Criteria for Phase 0

Phase 0 is complete when all of the following are confirmed:

1. formal repository top-level structure
2. RelayPackage structure
3. all INDEX schemas
4. Delete schema
5. picture naming rules
6. merge chunking rules
7. Refresh Component responsibilities
8. formal Tool boundary
9. validation problem levels
10. time / ordering / version rules

---

## 15. Fixed Development Order After Phase 0

After protocol freezing, the recommended order is fixed as:

1. **Phase 1: build the new repository skeleton**
2. **Phase 2: implement Data_Merge_Tool**
3. **Phase 3: implement RelayPackage Refresh Component**
4. **Phase 4: prepare and test sample packages**
5. **Phase 5: connect frontend layer management / workflow export**

---

## 16. Suggested Minimal Example Layout

```text
Data_Spilt/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001.json

Data_Merge/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      chunk_001.json

Picture/
  INDEX.json
  zth/
    RLE/
      INDEX.json
      RLE_0001/
        RLE_0001_1.jpg

RelayPackage/
  INDEX.json
  Delete.json
  Data_Spilt/
  Picture/
```

---

## 17. Notes

- `Data_Spilt` is intentionally spelled as `Spilt` here to match the current agreed naming in this protocol.
- If the repository later chooses to rename `Data_Spilt` to `Data_Split`, that must be treated as a separate protocol change and migration step, not an implicit adjustment inside Phase 0.

---
