# Migration Schema Reference

> All migration scripts: PostgreSQL table fields, .NET C# types, and PostgreSQL column types.
> Enums show only the values defined in C# source.
> All enum columns are nullable (NULL if not set in RavenDB).

---

## Table of Contents

| Script | PostgreSQL Table(s) |
|---|---|
| [applications](#applications) | `application_form_templates`, `applications` |
| [artefacts](#artefacts) | `artefact_tags`, `artefacts` |
| [assessments](#assessments) | `assessment_tags`, `assessments` |
| [asset_views](#asset_views) | `asset_views` |
| [attendance_events](#attendance_events) | `attendance_event` |
| [calendar_rules](#calendar_rules) | `calendar_rules` |
| [circulation_views](#circulation_views) | `circulation_views` |
| [commits](#commits) | `commits_*` (dynamic) |
| [content_tags](#content_tags) | `content_tags` |
| [courses](#courses) | `course` |
| [emails](#emails) | `email` |
| [exams](#exams) | `exam` |
| [fees](#fees) | `fee`, `fee_transaction` |
| [gradings](#gradings) | `gradings` |
| [image_tags](#image_tags) | `image_tags` |
| [institute_calendars](#institute_calendars) | `institute_calendars` |
| [inventory](#inventory) | `inventory_item_views`, `inventory_journal_views` |
| [ledger_account_views](#ledger_account_views) | `ledger_account_views` |
| [material_views](#material_views) | `material_views` |
| [member_views](#member_views) | `member_views` |
| [personas](#personas) | `persona` |
| [questions](#questions) | `qa_tags`, `questions`, `random_question_submissions` |
| [receipts](#receipts) | `receipts` |
| [seat_matrices](#seat_matrices) | `seat_matrices` |
| [sms](#sms) | `sms`, `sms_message` |
| [staffs](#staffs) | `staffs` |
| [students](#students) | `organization`, `institute`, `student` |
| [topics](#topics) | `topics` |
| [users](#users) | `users` |
| [voucher_views](#voucher_views) | `voucher_views` |

---

## applications

**Script:** `applications_ravendb_to_postgres_migrate.py`
**RavenDB Collections:** `ApplicationFormTemplates`, `Applications`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `application_form_template_status_enum` | `Active`, `Published`, `Disabled` | `ApplicationFormTemplateStatusEnum` | Active=1, Published=70, Disabled=99 |
| `residential_status_enum` | `Indian`, `PIO_OCI`, `NRI` | `ResidentialStatusEnum` | Indian=10, PIO_OCI=20, NRI=30 |
| `applicant_category_enum` | `GM`, `OBC`, `SC`, `ST` | `ApplicantCategoryEnum` | — |
| `applicant_gender_enum` | `Female`, `Male`, `NoInfo` | `GenderEnum` | — |
| `application_status_enum` | `WIP`, `Selected`, `Submitted`, `Shortlisted`, `Admitted`, `Rejected`, `OptedIn`, `OptedOut`, `Declined` | `ApplicationStatusEnum` | WIP=10, Selected=15, Submitted=20, Shortlisted=25, Admitted=30, Rejected=35, OptedIn=40, OptedOut=45, Declined=50 |

---

### Table: `application_form_templates`

**C# Source:** `ApplicationFormTemplate : Entity`

| PG Column | C# Field | C# Type | PG Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID PRIMARY KEY` |
| `title` | `Title` | `string` | `VARCHAR(255)` |
| `description` | `Description` | `string` | `TEXT` |
| `options` | `Options` | `AdmissionFormOptions` (object) | `JSONB` |
| `start_date` | `StartDate` | `DateTime` | `TIMESTAMPTZ` |
| `end_date` | `EndDate` | `DateTime` | `TIMESTAMPTZ` |
| `status` | `Status` | `ApplicationFormTemplateStatusEnum` | `application_form_template_status_enum` |
| `shortlists` | `Shortlists` | `List<Shortlist>` | `JSONB` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

### Table: `applications`

**C# Source:** `Application : Entity`

| PG Column | C# Field | C# Type | PG Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID PRIMARY KEY` |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `email` | `Email` | `string` | `VARCHAR(255)` |
| `mobile` | `Mobile` | `string` | `VARCHAR(50)` |
| `dob` | `DOB` | `DateTime` | `TIMESTAMPTZ` |
| `residential_status` | `ResidentialStatus` | `ResidentialStatusEnum` | `residential_status_enum` |
| `category` | `Category` | `ApplicantCategoryEnum` | `applicant_category_enum` |
| `gender` | `Gender` | `GenderEnum` | `applicant_gender_enum` |
| `address` | `Address` | `ApplicantAddress` (object) | `JSONB` |
| `hsc` | `HSC` | `AcademicHistory` (object) | `JSONB` |
| `ssc` | `SSC` | `AcademicHistory` (object) | `JSONB` |
| `father_details` | `FatherDetails` | `ParentDetails` (object) | `JSONB` |
| `mother_details` | `MotherDetails` | `ParentDetails` (object) | `JSONB` |
| `guardian_details` | `GuardianDetails` | `ParentDetails` (object) | `JSONB` |
| `applied_for` | `AppliedFor` | `AppliedFor` (object) | `JSONB` |
| `payment` | `Payment` | `Payment` (object) | `JSONB` |
| `photo_url` | `PhotoURL` | `string` | `TEXT` |
| `aadhar_url` | `AadharURL` | `string` | `TEXT` |
| `hsc_marks_card_url` | `HSCMarksCardURL` | `string` | `TEXT` |
| `ssc_marks_card_url` | `SSCMarksCardURL` | `string` | `TEXT` |
| `caste_certificate_url` | `CasteCertificateURL` | `string` | `TEXT` |
| `domicile_certificate_url` | `DomicileCertificateURL` | `string` | `TEXT` |
| `birth_certificate_url` | `BirthCertificateURL` | `string` | `TEXT` |
| `transfer_certificate_url` | `TransferCertificateURL` | `string` | `TEXT` |
| `leaving_certificate_url` | `LeavingCertificateURL` | `string` | `TEXT` |
| `application_form_template_id` | `ApplicationFormTemplateId` | `string` (UUID) | `UUID` |
| `submitted_on` | `SubmittedOn` | `DateTime` | `TIMESTAMPTZ` |
| `application_number` | `ApplicationNumber` | `int` | `INTEGER` |
| `shortlisted_in` | `ShortlistedIn` | `int` | `INTEGER` |
| `doa` | `DOA` | `DateTime` | `TIMESTAMPTZ` |
| `application_status` | `ApplicationStatus` | `ApplicationStatusEnum` | `application_status_enum` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## artefacts

**Script:** rtefacts_ravendb_to_postgres_migrate.py
**RavenDB Collections:** ArtefactTags, Artefacts

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| 	ag_status_enum | Unknown, Active, Disabled | TagStatusEnum | Unknown=0, Active=1, Disabled=99 |
| rtefact_status_enum | Unknown, Active, Etl, Published, PublishedToPublic, Uploaded, Downloaded, Disabled | ArtefactStatusEnum | Unknown=0, Active=1, Etl=60, Published=70, PublishedToPublic=75, Uploaded=80, Downloaded=90, Disabled=99 |

---

### Table: rtefact_tags

**C# Source:** ArtefactTag : Entity

| PG Column | C# Field | C# Type | PG Type |
|---|---|---|---|
| id | Id | string (UUID) | UUID PRIMARY KEY |
| 
ame | Name | string | VARCHAR(150) |
| predefined | Predefined | ool | BOOLEAN |
| csn | CSN | string | VARCHAR(100) |
| meta | Meta | Dictionary<string, string> | JSONB |
| status | Status | TagStatusEnum | 	ag_status_enum |
| owner_id | OwnerId *(Entity)* | string (UUID) | UUID |
| parent_id | ParentId *(Entity)* | string (UUID) | UUID |
| created_on | CreatedOn *(Entity)* | DateTime | TIMESTAMPTZ |
| created_by | CreatedBy *(Entity)* | string (UUID) | UUID |
| modified_on | ModifiedOn *(Entity)* | DateTime? | TIMESTAMPTZ |
| modified_by | ModifiedBy *(Entity)* | string (UUID) | UUID |

---

### Table: rtefacts

**C# Source:** Artefact : Entity

| PG Column | C# Field | C# Type | PG Type |
|---|---|---|---|
| id | Id | string (UUID) | UUID PRIMARY KEY |
| url | Url | string | TEXT |
| 	itle | Title | string | VARCHAR(250) |
| description | Description | string | TEXT |
| meta_data | MetaData | Dictionary<string, string> | JSONB |
| 	ags | Tags | List<string> | TEXT[] |
| mime_type | MimeType | string | VARCHAR(100) |
| ile_name | FileName | string | VARCHAR(250) |
| ile_size | FileSize | double | DOUBLE PRECISION |
| status | Status | ArtefactStatusEnum | rtefact_status_enum |
| sha1 | SHA1 | string | VARCHAR(100) |
| model | Model | string | TEXT |
| 	emplate | Template | string | TEXT |
| csv | Csv | string | TEXT |
| change_set | ChangeSet | List<ChangeRef> | JSONB |
| comments | Comments | List<Comment> | JSONB |
| ideo_links | VideoLinks | List<VideoLink> | JSONB |
| data_attributes | DataAttributes | List<DataAttribute> | JSONB |
| published_on | PublishedOn | DateTime | TIMESTAMPTZ |
| public_urls | PublicUrls | List<string> | TEXT[] |
| 	humbnails | Thumbnails | List<string> | TEXT[] |
| owner_id | OwnerId *(Entity)* | string (UUID) | UUID |
| parent_id | ParentId *(Entity)* | string (UUID) | UUID |
| created_on | CreatedOn *(Entity)* | DateTime | TIMESTAMPTZ |
| created_by | CreatedBy *(Entity)* | string (UUID) | UUID |
| modified_on | ModifiedOn *(Entity)* | DateTime? | TIMESTAMPTZ |
| modified_by | ModifiedBy *(Entity)* | string (UUID) | UUID |

> **Null rule:** All JSONB and TEXT[] columns store NULL if the field is null/missing in RavenDB.

---

> **Note:** Remaining scripts (assessments, asset_views, attendance_events, calendar_rules, etc.) will be added in subsequent sections below.
