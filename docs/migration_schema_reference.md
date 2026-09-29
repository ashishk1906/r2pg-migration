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


---

## assessments

**Script:** `assessments_ravendb_to_postgres_migrate.py`
**RavenDB Collections:** `AssessmentTags`, `Assessments`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |
| `assessment_status_enum` | `Unknown`, `Active`, `WIP`, `Published`, `Archived`, `Disabled` | `AssessmentStatusEnum` | `Unknown` = 0, `Active` = 1, `WIP` = 40, `Published` = 50, `Archived` = 80, `Disabled` = 99 |

---

### Table: `assessment_tags`

**PostgreSQL Table:** `assessment_tags`
**RavenDB Source:** `AssessmentTags` (Entity: `AssessmentTag : Entity`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(150)` |
| `predefined` | `Predefined` | `bool` | `BOOLEAN` |
| `csn` | `CSN` | `string` | `VARCHAR(100)` |
| `meta` | `Meta` | `Dictionary<string, string>` | `JSONB` |
| `status` | `Status` | `TagStatusEnum` | `tag_status_enum` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

### Table: `assessments`

**PostgreSQL Table:** `assessments`
**RavenDB Source:** `Assessments` (Entity: `Assessment : Entity`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `total_marks` | `TotalMarks` | `decimal` | `NUMERIC(14, 2)` |
| `description` | `Description` | `string` | `TEXT` |
| `subject` | `Subject` | `string` | `VARCHAR(150)` |
| `subject_code` | `SubjectCode` | `string` | `VARCHAR(50)` |
| `duration` | `Duration` | `int` | `INT` |
| `sections` | `Sections` | `List<AssessmentSection>` | `JSONB` |
| `status` | `Status` | `AssessmentStatusEnum` | `assessment_status_enum` |
| `multiple_attempts` | `MultipleAttempts` | `bool` | `BOOLEAN` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |


---

## asset_views

**Script:** `asset_views_ravendb_to_postgres_migrate.py`
**RavenDB Collection:** `AssetViews`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `asset_status_enum` | `Active`, `Cleared`, `Disabled` | `AssetStatusEnum` | `Active` = 1, `Cleared` = 90, `Disabled` = 99 |

---

### Table: `asset_views`

**PostgreSQL Table:** `asset_views`
**RavenDB Source:** `AssetViews` (C# `AssetView : IReadModelAssets`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `tracking_id` | `TrackingId` | `string` | `VARCHAR(100)` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `location` | `Location` | `string` | `VARCHAR(250)` |
| `attributes` | `Attributes` | `string` (JSON) | `JSONB` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `value` | `Value` | `decimal` | `NUMERIC(18, 2)` |
| `last_maintenance` | `LastMaintenance` | `Maintenance` | `JSONB` |
| `current_warranty` | `CurrentWarranty` | `Warranty` | `JSONB` |
| `status` | `Status` | `AssetStatusEnum` | `asset_status_enum` |
| `under_warranty` | `UnderWarranty` | `bool` | `BOOLEAN` |


---

## attendance_events

**Script:** `attendance_events_ravendb_to_postgres_migrate.py`
**RavenDB Collection:** `AttendanceEvents`

### Enums

*None* (`Attendance` is plain `string` in C#).

---

### Table: `attendance_event`

**PostgreSQL Table:** `attendance_event`
**RavenDB Source:** `AttendanceEvents` (C# `AttendanceEvent : Entity`)
**Primary Key:** `id` (`VARCHAR(100)`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` | `VARCHAR(100)` PRIMARY KEY |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `course_id` | `CourseId` | `string` (UUID) | `UUID` |
| `term_name` | `TermName` | `string` | `VARCHAR(100)` |
| `section_name` | `SectionName` | `string` | `VARCHAR(50)` |
| `date` | `Date` | `DateTime` | `TIMESTAMPTZ` |
| `period_no` | `PeriodNo` | `int` | `INTEGER` |
| `subject_name` | `SubjectName` | `string` | `VARCHAR(200)` |
| `is_optional_subject` | `IsOptionalSubject` | `bool` | `BOOLEAN` |
| `student_id` | `StudentId` | `string` (UUID) | `UUID` |
| `staff_id` | `StaffId` | `string` | `VARCHAR(100)` |
| `attendance` | `Attendance` | `string` | `VARCHAR(50)` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## calendar_rules

**Script:** `calendar_rules_ravendb_to_postgres_migrate.py`
**RavenDB Collection:** `CalendarRules`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `calendar_rule_status_enum` | `Active`, `Disabled` | `CalendarRuleStatusEnum` | `Active` = 1, `Disabled` = 99 |
| `calendar_event_category_enum` | `Event`, `Holiday`, `WeeklyHoliday`, `Exam` | `CalendarEventCategoryEnum` | `Event` = 10, `Holiday` = 20, `WeeklyHoliday` = 30, `Exam` = 40 |

---

### Table: `calendar_rules`

**PostgreSQL Table:** `calendar_rules`
**RavenDB Source:** `CalendarRules` (C# `CalendarRule : Entity`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `title` | `Title` | `string` | `VARCHAR(255)` |
| `cron_expression` | `CronExpression` | `string` | `VARCHAR(100)` |
| `calendar_rule_status` | `CalendarRuleStatus` | `CalendarRuleStatusEnum` | `calendar_rule_status_enum` |
| `calendar_event_category` | `CalendarEventCategory` | `CalendarEventCategoryEnum` | `calendar_event_category_enum` |
| `weight` | `Weight` | `int` | `INTEGER` |
| `duration` | `Duration` | `decimal` | `NUMERIC(10, 2)` |
| `topic_id` | `TopicId` | `string` (UUID) | `UUID` |
| `user_id` | `UserId` | `string` (UUID) | `UUID` |
| `create_meeting_link` | `CreateMeetingLink` | `bool` | `BOOLEAN` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## circulation_views

**Script:** `circulation_views_ravendb_to_postgres_migrate.py`
**RavenDB Collection:** `CirculationViews`

### Enums

*None*

---

### Table: `circulation_views`

**PostgreSQL Table:** `circulation_views`
**RavenDB Source:** `CirculationViews` (C# `CirculationView : IReadModelLibrary`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `tracking_id` | `TrackingId` | `string` | `VARCHAR(100)` |
| `issued_on` | `IssuedOn` | `DateTime` | `TIMESTAMPTZ` |
| `received_on` | `ReceivedOn` | `DateTime` | `TIMESTAMPTZ` |
| `due_on` | `DueOn` | `DateTime` | `TIMESTAMPTZ` |
| `reissued_on` | `ReissuedOn` | `DateTime` | `TIMESTAMPTZ` |
| `issued_to` | `IssuedTo` | `string` | `VARCHAR(100)` |

---

## commits

**Script:** `commits_ravendb_to_postgres_migrate.py`
**RavenDB Collections:** `CommitAssets`, `Commits`, `CommitAcs`

### Enums

*None*

---

### Tables: `commit_asset`, `commits`, `commit_ac`

**PostgreSQL Tables:** `commit_asset`, `commits`, `commit_ac`
**RavenDB Sources:**
- `commit_asset` $\leftarrow$ `CommitAssets` (C# `CommitAssets`)
- `commits` $\leftarrow$ `Commits` (C# `Commit`)
- `commit_ac` $\leftarrow$ `CommitAcs` (C# `CommitAc`)
**Primary Key:** `id` (`UUID`)

All three tables share the same Common Commit Wrapper schema:

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `aggregate_id` | `AggregateId` | `string` (UUID) | `UUID` |
| `version` | `Version` | `int` | `INTEGER` |
| `user_id` | `UserId` | `string` (UUID) | `UUID` |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `timestamp` | `TimeStamp` | `DateTime` | `TIMESTAMPTZ` |
| `event_message` | `EventMessage` | `object` | `JSONB` |

---

## content_tags

**Script:** `content_tags_ravendb_to_postgres_migrate.py`
**RavenDB Collection:** `ContentTags`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `content_tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table: `content_tags`

**PostgreSQL Table:** `content_tags`
**RavenDB Source:** `ContentTags` (C# `ContentTag : Entity`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `predefined` | `Predefined` | `bool` | `BOOLEAN` |
| `csn` | `CSN` | `string` | `VARCHAR(50)` |
| `meta` | `Meta` | `Dictionary<string, string>` | `JSONB` |
| `status` | `Status` | `TagStatusEnum` | `content_tag_status_enum` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

> **Note:** Remaining scripts (courses, emails, exams, fees, etc.) will be added in subsequent sections below.



