"""
Pydantic models for structured CMS requirement extraction.
"""

from pydantic import BaseModel, Field


class CMSRequirements(BaseModel):
    """Structured representation of requirements extracted from a CMS document."""

    report_name: str = Field(
        default="",
        description="The official name or title of the CMS report.",
    )
    report_type: str = Field(
        default="",
        description="The type/category of report (e.g., quality measure, cost report, enrollment).",
    )
    reporting_entities: list[str] = Field(
        default_factory=list,
        description="Organizations or entity types required to submit this report.",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description="Quantitative measures, KPIs, or data points the report must contain.",
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description="Grouping or segmentation axes (e.g., by state, provider type, time period).",
    )
    filters: list[str] = Field(
        default_factory=list,
        description="Criteria used to include or narrow the data population.",
    )
    business_rules: list[str] = Field(
        default_factory=list,
        description="Logic, calculations, or conditional rules governing the report.",
    )
    exclusions: list[str] = Field(
        default_factory=list,
        description="Populations, data points, or conditions explicitly excluded.",
    )
    reporting_frequency: str = Field(
        default="",
        description="How often the report must be submitted (e.g., monthly, quarterly, annually).",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Additional observations, caveats, or context from the document.",
    )


class OrgDecision(BaseModel):
    """A single organizational decision made by an SME."""

    decision_id: str = Field(
        default="",
        description="Unique identifier for this decision.",
    )
    type: str = Field(
        default="",
        description="One of: terminology_clarification, business_rule, reporting_preference.",
    )
    source_term: str = Field(
        default="",
        description="The original term from the CMS document.",
    )
    mapped_term: str = Field(
        default="",
        description="The organization's preferred term or interpretation.",
    )
    description: str = Field(
        default="",
        description="Explanation of the decision and its impact.",
    )
    timestamp: str = Field(
        default="",
        description="ISO-8601 timestamp of when the decision was made.",
    )
    author: str = Field(
        default="SME",
        description="Who made or last modified this decision.",
    )
    version: int = Field(
        default=1,
        description="Current version number of this decision.",
    )
    change_history: list[dict] = Field(
        default_factory=list,
        description="Versioned history of changes to this decision.",
    )


class SMEChatResponse(BaseModel):
    """Structured response from the SME collaboration AI."""

    reply: str = Field(
        description="The AI's conversational response to the user.",
    )
    is_decision: bool = Field(
        default=False,
        description="True if the user's statement constitutes an actionable decision.",
    )
    decision_type: str = Field(
        default="",
        description="One of: terminology_clarification, business_rule, reporting_preference. Empty if not a decision.",
    )
    source_term: str = Field(
        default="",
        description="The original term from the CMS document (empty if not a decision).",
    )
    mapped_term: str = Field(
        default="",
        description="The organization's preferred term (empty if not a decision).",
    )
    decision_description: str = Field(
        default="",
        description="Explanation of the decision (empty if not a decision).",
    )


class FHIRCatalogEntry(BaseModel):
    """A single entry in the FHIR semantic catalog."""

    resource: str = Field(description="FHIR resource type (e.g., Patient, Encounter).")
    profile: str = Field(description="US Core profile URL.")
    business_meaning: str = Field(description="Plain-language explanation of the resource.")
    common_fields: list[str] = Field(default_factory=list, description="Key FHIR fields.")
    cms_concepts: list[str] = Field(default_factory=list, description="CMS concepts this resource covers.")


class FHIRMapping(BaseModel):
    """A single CMS concept → FHIR mapping produced by Gemini."""

    concept: str = Field(description="The CMS concept being mapped.")
    fhir_resource: str = Field(description="Target FHIR resource type.")
    fhir_field: str = Field(description="Specific FHIR field within the resource.")
    confidence: str = Field(description="Confidence level: high, medium, or low.")
    reasoning: str = Field(description="Explanation of why this mapping was chosen.")


class FHIRMappingSet(BaseModel):
    """Container for a batch of FHIR mappings returned by Gemini."""

    mappings: list[FHIRMapping] = Field(
        default_factory=list,
        description="List of CMS concept to FHIR resource mappings.",
    )


# ── Analytics / Star Schema Models ───────────────────────────────────

class TableColumn(BaseModel):
    """A column in a fact or dimension table."""

    name: str = Field(description="Column name (snake_case).")
    data_type: str = Field(description="Data type (e.g., VARCHAR, INTEGER, DATE, DECIMAL).")
    source_fhir_field: str = Field(default="", description="FHIR field this column derives from.")
    description: str = Field(default="", description="Business description.")


class FactTable(BaseModel):
    """A fact table in the star schema."""

    name: str = Field(description="Table name (e.g., FactEncounter).")
    source_fhir_resource: str = Field(description="FHIR resource this derives from.")
    description: str = Field(default="", description="Business purpose.")
    grain: str = Field(default="", description="What one row represents.")
    columns: list[TableColumn] = Field(default_factory=list, description="Table columns.")


class DimensionTable(BaseModel):
    """A dimension table in the star schema."""

    name: str = Field(description="Table name (e.g., DimPatient).")
    source_fhir_resource: str = Field(default="", description="FHIR resource this derives from.")
    description: str = Field(default="", description="Business purpose.")
    columns: list[TableColumn] = Field(default_factory=list, description="Table columns.")


class Relationship(BaseModel):
    """A foreign key relationship between a fact and dimension table."""

    fact_table: str = Field(description="Fact table name.")
    dimension_table: str = Field(description="Dimension table name.")
    join_key: str = Field(description="Foreign key column name.")
    relationship_type: str = Field(default="many-to-one", description="Relationship cardinality.")
    is_active: bool = Field(default=True, description="Whether the relationship is active in Power BI.")


class MetricDef(BaseModel):
    """A business metric that can be computed from the star schema."""

    name: str = Field(description="Metric name (snake_case).")
    description: str = Field(default="", description="Business definition.")
    formula: str = Field(default="", description="SQL-like formula or calculation logic.")
    fact_table: str = Field(default="", description="Source fact table.")
    dimensions: list[str] = Field(default_factory=list, description="Dimensions for slicing.")


class AttributeDef(BaseModel):
    """A drill-down attribute in the analytics model."""

    name: str = Field(description="Attribute name.")
    table: str = Field(default="", description="Table this attribute belongs to.")
    drill_path: list[str] = Field(default_factory=list, description="Ordered drill-down hierarchy.")
    description: str = Field(default="", description="What this attribute represents.")


class AnalyticsModel(BaseModel):
    """Complete star schema analytics model."""

    fact_tables: list[FactTable] = Field(default_factory=list, description="Fact tables.")
    dimension_tables: list[DimensionTable] = Field(default_factory=list, description="Dimension tables.")
    relationships: list[Relationship] = Field(default_factory=list, description="FK relationships.")
    metrics: list[MetricDef] = Field(default_factory=list, description="Business metrics.")
    attributes: list[AttributeDef] = Field(default_factory=list, description="Drill-down attributes.")


# ── Report Definition / Power BI Models ──────────────────────────────

class ReportVisual(BaseModel):
    """A single visual element in a Power BI report page."""

    title: str = Field(description="Visual title displayed on the report.")
    visual_type: str = Field(
        description="Power BI visual type (e.g., card, bar_chart, line_chart, table, "
        "donut_chart, treemap, matrix, kpi, gauge, stacked_bar, slicer).",
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description="Dimension columns used (axis, legend, rows).",
    )
    measures: list[str] = Field(
        default_factory=list,
        description="Measure names or DAX expressions used as values.",
    )
    business_reason: str = Field(
        default="",
        description="Why this visual is included and what insight it provides.",
    )


class ReportPage(BaseModel):
    """A single page/tab in the Power BI report."""

    page_name: str = Field(description="Page tab name.")
    purpose: str = Field(default="", description="What this page is for.")
    visuals: list[ReportVisual] = Field(
        default_factory=list,
        description="Visuals on this page.",
    )


class ReportFilter(BaseModel):
    """A report-level or page-level filter/slicer."""

    name: str = Field(description="Filter name.")
    field: str = Field(default="", description="Table.Column the filter targets.")
    filter_type: str = Field(
        default="slicer",
        description="Filter type (slicer, dropdown, date_range, relative_date).",
    )
    default_value: str = Field(default="", description="Default value if any.")
    scope: str = Field(
        default="report",
        description="Scope: report (all pages) or page (single page).",
    )


class ReportMeasure(BaseModel):
    """A DAX measure defined for the report."""

    name: str = Field(description="Measure name.")
    dax_expression: str = Field(default="", description="DAX formula.")
    format_string: str = Field(default="", description="Display format (e.g., #,##0, 0.0%).")
    description: str = Field(default="", description="Business definition.")
    home_table: str = Field(default="", description="Table this measure belongs to.")


class DrillthroughPage(BaseModel):
    """A drillthrough detail page in the report."""

    page_name: str = Field(description="Drillthrough page name.")
    purpose: str = Field(default="", description="What detail this page exposes.")
    drillthrough_field: str = Field(
        default="",
        description="The field users right-click on to drill through.",
    )
    visuals: list[ReportVisual] = Field(
        default_factory=list,
        description="Visuals on the drillthrough page.",
    )


class ReportDefinition(BaseModel):
    """Complete Power BI report specification."""

    report_name: str = Field(default="", description="Report title.")
    pages: list[ReportPage] = Field(default_factory=list, description="Report pages/tabs.")
    filters: list[ReportFilter] = Field(default_factory=list, description="Report-level filters.")
    visuals: list[ReportVisual] = Field(
        default_factory=list,
        description="Top-level visuals shared across pages (kept for schema compat).",
    )
    measures: list[ReportMeasure] = Field(default_factory=list, description="DAX measures.")
    drillthrough_pages: list[DrillthroughPage] = Field(
        default_factory=list,
        description="Drillthrough detail pages.",
    )


# ── Reporting Intent Models ──────────────────────────────────────────

class ReportingIntent(BaseModel):
    """Classification of a single CMS requirement's reporting intent."""

    requirement: str = Field(description="The CMS requirement text being classified.")
    intent: str = Field(
        description="Intent category: detail_listing, kpi, trend_analysis, "
        "comparison_analysis, cross_tabulation, data_submission, "
        "data_quality, or compliance_monitoring.",
    )
    recommended_visual: str = Field(
        default="",
        description="Recommended Power BI visual type for this intent.",
    )
    required_columns: list[str] = Field(
        default_factory=list,
        description="Star schema columns needed to fulfill this requirement.",
    )
    reasoning: str = Field(
        default="",
        description="Explanation of why this intent was chosen.",
    )


class ReportingIntentSet(BaseModel):
    """Container for a batch of reporting intents returned by Gemini."""

    intents: list[ReportingIntent] = Field(
        default_factory=list,
        description="List of classified reporting intents.",
    )


# ── Data Dictionary Models ───────────────────────────────────────────

class DataDictionaryEntry(BaseModel):
    """A single entry in the source-to-report data dictionary."""

    report_field: str = Field(
        description="The field name as it appears in the final report.",
    )
    business_definition: str = Field(
        default="",
        description="Plain-language business definition of this field.",
    )
    classification: str = Field(
        default="",
        description="Data classification: FHIR, Derived, or Non-FHIR.",
    )
    source_type: str = Field(
        default="",
        description="Source type: Direct, Derived, or SME Rule.",
    )
    source_resource: str = Field(
        default="",
        description="The FHIR resource or star schema table this field originates from.",
    )
    source_field: str = Field(
        default="",
        description="The specific source field or column (e.g., Patient.identifier, "
        "FactObservation.disposition).",
    )
    transformation_rule: str = Field(
        default="",
        description="Any transformation, calculation, or business rule applied "
        "to derive the report value from the source.",
    )
    report_usage: str = Field(
        default="",
        description="How this field is used in the report: Table, KPI, Trend, "
        "Matrix, or Export.",
    )


class DataDictionarySet(BaseModel):
    """Container for a batch of data dictionary entries returned by Gemini."""

    entries: list[DataDictionaryEntry] = Field(
        default_factory=list,
        description="List of data dictionary entries.",
    )


# ── Measure Generator Models ────────────────────────────────────────

class MeasureEntry(BaseModel):
    """A single business measure generated from the report definition."""

    measure_name: str = Field(
        description="The measure name (business-friendly, e.g., 'Total Organization Determinations').",
    )
    measure_type: str = Field(
        default="",
        description="Measure type: Count, Sum, Average, Percentage, Ratio, Distinct Count, or Trend.",
    )
    classification: str = Field(
        default="",
        description="Measure classification: Base Measure, Derived Measure, or KPI.",
    )
    business_definition: str = Field(
        default="",
        description="Plain-language explanation of what this measure represents.",
    )
    formula_description: str = Field(
        default="",
        description="Human-readable description of the calculation logic or DAX expression.",
    )
    source_tables: list[str] = Field(
        default_factory=list,
        description="Star schema tables this measure draws from.",
    )
    source_fields: list[str] = Field(
        default_factory=list,
        description="Star schema columns consumed by this measure.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Names of other measures this measure depends on.",
    )
    report_pages: list[str] = Field(
        default_factory=list,
        description="Names of report pages where this measure is used.",
    )
    visuals_used_in: list[str] = Field(
        default_factory=list,
        description="Titles of visuals where this measure is used.",
    )


class MeasureSet(BaseModel):
    """Container for a batch of measures returned by Gemini."""

    measures: list[MeasureEntry] = Field(
        default_factory=list,
        description="List of generated business measures.",
    )


# ── DAX Generator Models ─────────────────────────────────────────────

class DAXEntry(BaseModel):
    """A single Power BI DAX measure."""

    measure_name: str = Field(
        description="The measure name (business-friendly, matching measures.json).",
    )
    business_definition: str = Field(
        default="",
        description="Plain-language explanation of what this measure represents.",
    )
    dax_expression: str = Field(
        default="",
        description="The actual DAX expression (e.g., [Adverse Decisions] / [Total Decisions]).",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Names of other DAX measures this measure depends on.",
    )


class DAXSet(BaseModel):
    """Container for a batch of DAX measures returned by Gemini."""

    dax_measures: list[DAXEntry] = Field(
        default_factory=list,
        description="List of generated DAX measures.",
    )


# ── FRS (Functional Requirements Specification) Models ───────────────

class FRSKPIDefinition(BaseModel):
    """A KPI definition extracted from the FRS."""
    name: str = Field(description="KPI name.")
    definition: str = Field(default="", description="Business definition of the KPI.")
    formula: str = Field(default="", description="Calculation formula or rule.")
    target: str = Field(default="", description="Target or threshold value.")
    visual_type: str = Field(default="", description="Expected visualization type.")


class FRSPageExpectation(BaseModel):
    """An expected report page from the FRS."""
    page_name: str = Field(description="Expected page/tab name.")
    purpose: str = Field(default="", description="What this page should show.")
    expected_visuals: list[str] = Field(default_factory=list, description="Expected visual types on this page.")
    expected_kpis: list[str] = Field(default_factory=list, description="KPIs expected on this page.")


class FRSRequirements(BaseModel):
    """Structured requirements extracted from a Functional Requirements Specification."""
    business_definitions: list[dict] = Field(
        default_factory=list,
        description="Business terms and their definitions from the FRS.",
    )
    kpi_definitions: list[FRSKPIDefinition] = Field(
        default_factory=list,
        description="KPI definitions extracted from the FRS.",
    )
    page_expectations: list[FRSPageExpectation] = Field(
        default_factory=list,
        description="Expected report pages and their contents.",
    )
    visualization_expectations: list[dict] = Field(
        default_factory=list,
        description="Expected visualization types and configurations.",
    )
    filters: list[str] = Field(
        default_factory=list,
        description="Expected report filters from the FRS.",
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description="Expected dimensions / slicing axes from the FRS.",
    )
    drillthrough_requirements: list[str] = Field(
        default_factory=list,
        description="Drillthrough page requirements.",
    )
    user_expectations: list[str] = Field(
        default_factory=list,
        description="User-facing interaction expectations.",
    )


class MergeConflict(BaseModel):
    """A conflict between CMS and FRS requirements."""
    field: str = Field(description="The field or concept with a conflict.")
    cms_value: str = Field(default="", description="Value from CMS requirement.")
    frs_value: str = Field(default="", description="Value from FRS requirement.")
    conflict_type: str = Field(default="", description="Type: definition_mismatch, missing_in_cms, missing_in_frs.")
    resolution: str = Field(default="", description="How the conflict was resolved, if at all.")
    resolved: bool = Field(default=False, description="Whether this conflict has been resolved.")


class MergedRequirementModel(BaseModel):
    """Merged model combining CMS + FRS requirements."""
    cms_requirements: dict = Field(default_factory=dict, description="Original CMS requirements.")
    frs_requirements: dict = Field(default_factory=dict, description="Original FRS requirements.")
    merged_metrics: list[str] = Field(default_factory=list, description="Unified metric list.")
    merged_dimensions: list[str] = Field(default_factory=list, description="Unified dimension list.")
    merged_filters: list[str] = Field(default_factory=list, description="Unified filter list.")
    merged_business_rules: list[str] = Field(default_factory=list, description="Unified business rules.")
    conflicts: list[MergeConflict] = Field(default_factory=list, description="Detected conflicts.")
    assumptions: list[dict] = Field(default_factory=list, description="Assumptions made during merge.")

