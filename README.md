# OpenRIAMap-Data

Formal data repository skeleton for OpenRIAMap.

## Structure
- `Data_Spilt`: source feature data
- `Data_Merge`: runtime merged data
- `Picture`: attached picture resources
- `Data_Merge_Tool`: maintenance tools
- `docs`: repository specifications

## Detected Class Codes from current src baseline
- Standard classes: `STA`, `PLF`, `RLE`, `PFB`, `STB`, `SBP`, `STF`, `ROD`, `TPP`, `WRP`, `TRP`, `BUD`, `FLR`
- Special classes with Kind subdirectories: `ISG`, `ISL`, `ISP`
- Current detected special Kinds: `ADM`, `NGF`

## Current world IDs
- `zth`, `naraku`, `houtu`, `eden`, `laputa`, `yunduan`

## Specifications
See:
- `docs/README_SPEC_Phase0_RelayPackage_NewRepository_v1.md`
- `docs/INITIALIZATION_NOTES.md`
- `docs/DETECTED_CLASS_TYPES_FROM_SRC.md`

## Workflow
1. Prepare RelayPackage
2. Refresh and validate package
3. Apply package through Data_Merge_Tool
4. Rebuild merge outputs
