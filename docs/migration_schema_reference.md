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

**Script:** `artefacts_ravendb_to_postgres_migrate.py`
**RavenDB Collections:** `ArtefactTags`, `Artefacts`

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |
| `artefact_status_enum` | `Unknown`, `Active`, `Etl`, `Published`, `PublishedToPublic`, `Uploaded`, `Downloaded`, `Disabled` | `ArtefactStatusEnum` | `Unknown` = 0, `Active` = 1, `Etl` = 60, `Published` = 70, `PublishedToPublic` = 75, `Uploaded` = 80, `Downloaded` = 90, `Disabled` = 99 |

---

### Table: `artefact_tags`

**PostgreSQL Table:** `artefact_tags`
**RavenDB Source:** `ArtefactTags` (Entity: `ArtefactTag : Entity`)
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

### Table: `artefacts`

**PostgreSQL Table:** `artefacts`
**RavenDB Source:** `Artefacts` (Entity: `Artefact : Entity`)
**Primary Key:** `id` (`UUID`)

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `url` | `Url` | `string` | `TEXT` |
| `title` | `Title` | `string` | `VARCHAR(250)` |
| `description` | `Description` | `string` | `TEXT` |
| `meta_data` | `MetaData` | `Dictionary<string, string>` | `JSONB` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `mime_type` | `MimeType` | `string` | `VARCHAR(100)` |
| `file_name` | `FileName` | `string` | `VARCHAR(250)` |
| `file_size` | `FileSize` | `double` | `DOUBLE PRECISION` |
| `status` | `Status` | `ArtefactStatusEnum` | `artefact_status_enum` |
| `sha1` | `SHA1` | `string` | `VARCHAR(100)` |
| `model` | `Model` | `string` | `TEXT` |
| `template` | `Template` | `string` | `TEXT` |
| `csv` | `Csv` | `string` | `TEXT` |
| `change_set` | `ChangeSet` | `List<ChangeRef>` | `JSONB` |
| `comments` | `Comments` | `List<Comment>` | `JSONB` |
| `video_links` | `VideoLinks` | `List<VideoLink>` | `JSONB` |
| `data_attributes` | `DataAttributes` | `List<DataAttribute>` | `JSONB` |
| `published_on` | `PublishedOn` | `DateTime` | `TIMESTAMPTZ` |
| `public_urls` | `PublicUrls` | `List<string>` | `TEXT[]` |
| `thumbnails` | `Thumbnails` | `List<string>` | `TEXT[]` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |


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

## courses

**Script:** `courses_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Courses`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `edu_level_enum` | `Unknown`, `PreNursery`, `Nursery`, `School`, `UnderGraduate`, `Graduate`, `PostGraduate` | `EduLevelEnum` | `Unknown` = -1, `PreNursery` = 2, `Nursery` = 5, `School` = 10, `UnderGraduate` = 20, `Graduate` = 30, `PostGraduate` = 40 |
| `course_status_enum` | `Unknown`, `Active`, `Disabled` | `CourseStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table: `course`

**PostgreSQL Table:** `course`  
**RavenDB Source:** `Courses` (C# `Course : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(200)` |
| `branch` | `Branch` | `string` | `VARCHAR(100)` |
| `name_and_branch` | `NameAndBranch` | `string` | `VARCHAR(200)` |
| `edu_level` | `EduLevel` | `EduLevelEnum` | `edu_level_enum` |
| `edu_level_as_string` | `EduLevelAsString` | `string` | `VARCHAR(32)` |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `affiliation` | `Affiliation` | `string` | `VARCHAR(100)` |
| `status` | `Status` | `CourseStatusEnum` | `course_status_enum` |
| `status_as_string` | `StatusAsString` | `string` | `VARCHAR(32)` |
| `terms` | `Terms` | `List<Term>` | `JSONB` |
| `exam_subject_order` | `ExamSubjectOrder` | `List<string>` | `TEXT[]` |
| `sort_index` | `SortIndex` | `int` | `INTEGER` |
| `rank` | `Rank` | `int` | `INTEGER` |
| `seats_available` | `SeatsAvailable` | `int` | `INTEGER` |
| `program` | `Program` | `string` | `TEXT` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## emails

**Script:** `emails_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Emails`  

### Enums

*None (Standard string types used for type/from/subject)*

---

### Table: `email`

**PostgreSQL Table:** `email`  
**RavenDB Source:** `Emails` (C# `Email : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `recipients` | `Recipients` | `List<string>` | `TEXT[]` |
| `message` | `Message` | `string` | `TEXT` |
| `type` | `Type` | `string` | `VARCHAR(50)` |
| `from` | `From` | `string` | `VARCHAR(255)` |
| `subject` | `Subject` | `string` | `VARCHAR(500)` |
| `attachments` | `Attachments` | `List<Attachment>` | `JSONB` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## exams

**Script:** `exams_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Exams`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `exam_status_enum` | `Unknown`, `Active`, `Scheduled`, `Conducted`, `Locked`, `Disabled` | `ExamStatusEnum` | `Unknown` = 0, `Active` = 1, `Scheduled` = 10, `Conducted` = 20, `Locked` = 90, `Disabled` = 99 |

---

### Table: `exam`

**PostgreSQL Table:** `exam`  
**RavenDB Source:** `Exams` (C# `Exam : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(200)` |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `course_id` | `CourseId` | `string` (UUID) | `UUID` |
| `term` | `Term` | `string` | `VARCHAR(64)` |
| `section` | `Section` | `string` | `VARCHAR(32)` |
| `exam_contents` | `ExamContents` | `List<ExamContent>` | `JSONB` |
| `lock_history` | `LockHistory` | `List<LockEntry>` | `JSONB` |
| `attendance_list` | `AttendanceList` | `List<Attendance>` | `JSONB` |
| `remarks_list` | `RemarksList` | `List<Remark>` | `JSONB` |
| `status` | `Status` | `ExamStatusEnum` | `exam_status_enum` |
| `days_worked` | `DaysWorked` | `int` | `INTEGER` |
| `total_max_marks` | `TotalMaxMarks` | `decimal` | `NUMERIC(14, 2)` |
| `merge_index` | `MergeIndex` | `int` | `INTEGER` |
| `start_date` | `StartDate` | `DateTime` | `TIMESTAMPTZ` |
| `result_date` | `ResultDate` | `DateTime` | `TIMESTAMPTZ` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## fees

**Script:** `fees_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `Fees`, `FeeTxes`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `fee_status_enum` | `Unknown`, `Active`, `Disabled` | `FeeStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |
| `fee_tx_status_enum` | `Active`, `Disabled` | `FeeTxStatusEnum` | `Active` = 1, `Disabled` = 99 |

---

### Table: `fee`

**PostgreSQL Table:** `fee`  
**RavenDB Source:** `Fees` (C# `Fee : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(200)` |
| `name_lower` | `NameLower` | `string` | `VARCHAR(200)` |
| `display_text` | `DisplayText` | `string` | `VARCHAR(200)` |
| `amount` | `Amount` | `decimal` | `NUMERIC(14, 2)` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `collect_student_wise` | `CollectStudentWise` | `bool` | `BOOLEAN` |
| `student_list` | `StudentList` | `List<string>` | `TEXT[]` |
| `course_list` | `CourseList` | `List<string>` | `TEXT[]` |
| `installments` | `Installments` | `List<Installment>` | `JSONB` |
| `fines` | `Fines` | `List<Fine>` | `JSONB` |
| `is_tx_done` | `IsTxDone` | `bool` | `BOOLEAN` |
| `status` | `Status` | `FeeStatusEnum` | `fee_status_enum` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

### Table: `fee_transaction`

**PostgreSQL Table:** `fee_transaction`  
**RavenDB Source:** `FeeTxes` (C# `FeeTx : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `tx_no` | `TxNo` | `string` | `VARCHAR(100)` |
| `tx_date` | `TxDate` | `DateTime` | `TIMESTAMPTZ` |
| `student_id` | `StudentId` | `string` (UUID) | `UUID` |
| `installments_paid` | `InstallmentsPaid` | `List<FeeTxDto>` | `JSONB` |
| `fines_paid` | `FinesPaid` | `List<FeeFineDto>` | `JSONB` |
| `discounts` | `Discounts` | `List<FeeDiscountDto>` | `JSONB` |
| `fee_adjustment` | `FeeAdjustment` | `FeeAdjustmentDto` | `JSONB` |
| `payment_mode` | `PaymentMode` | `string` | `VARCHAR(64)` |
| `is_fine_paid` | `IsFinePaid` | `bool` | `BOOLEAN` |
| `is_discount_given` | `IsDiscountGiven` | `bool` | `BOOLEAN` |
| `has_fee_adjustment` | `HasFeeAdjustment` | `bool` | `BOOLEAN` |
| `is_opening_balance_adjusted` | `IsOpeningBalanceAdjusted` | `bool` | `BOOLEAN` |
| `ref_no` | `RefNo` | `string` | `VARCHAR(100)` |
| `amount` | `Amount` | `decimal` | `NUMERIC(14, 2)` |
| `status` | `Status` | `FeeTxStatusEnum` | `fee_tx_status_enum` |
| `paid_by` | `PaidBy` | `string` | `VARCHAR(100)` |
| `cheque_no` | `ChequeNo` | `string` | `VARCHAR(100)` |
| `bank_name` | `BankName` | `string` | `VARCHAR(200)` |
| `cheque_date` | `ChequeDate` | `DateTime` | `TIMESTAMPTZ` |
| `online_txn_ref_no` | `OnlineTxnRefNo` | `string` | `VARCHAR(100)` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## gradings

**Script:** `gradings_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Gradings`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `grading_status_enum` | `Active`, `Disabled` | `GradingStatusEnum` | `Active` = 1, `Disabled` = 99 |

---

### Table: `gradings`

**PostgreSQL Table:** `gradings`  
**RavenDB Source:** `Gradings` (C# `Grading : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `status` | `Status` | `GradingStatusEnum` | `grading_status_enum` |
| `grading_rules` | `GradingRules` | `List<GradingRule>` | `JSONB` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## image_tags

**Script:** `image_tags_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `ImageTags`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `image_tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table: `image_tags`

**PostgreSQL Table:** `image_tags`  
**RavenDB Source:** `ImageTags` (C# `ImageTag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `predefined` | `Predefined` | `bool` | `BOOLEAN` |
| `csn` | `CSN` | `string` | `VARCHAR(50)` |
| `meta` | `Meta` | `Dictionary<string, string>` | `JSONB` |
| `status` | `Status` | `TagStatusEnum` | `image_tag_status_enum` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## institute_calendars

**Script:** `institute_calendars_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `InstituteCalendars`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `calendar_event_category_enum` | `Event`, `Holiday`, `WeeklyHoliday`, `Exam` | `CalendarEventCategoryEnum` | `Event` = 10, `Holiday` = 20, `WeeklyHoliday` = 30, `Exam` = 40 |

---

### Table: `institute_calendars`

**PostgreSQL Table:** `institute_calendars`  
**RavenDB Source:** `InstituteCalendars` (C# `InstituteCalendar : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` *(Entity)* | `string` (UUID) | `UUID` PRIMARY KEY |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `event_name` | `EventName` | `string` | `VARCHAR(255)` |
| `event_category` | `EventCategory` | `CalendarEventCategoryEnum` | `calendar_event_category_enum` |
| `event_category_as_string` | `EventCategoryAsString` | `string` | `VARCHAR(100)` |
| `priority` | `Priority` | `int` | `INTEGER` |
| `audience` | `Audience` | `List<string>` | `TEXT[]` |
| `conducted_by` | `ConductedBy` | `List<string>` | `TEXT[]` |
| `event_dates` | `EventDates` | `List<Event>` | `JSONB` |
| `owner_id` | `OwnerId` *(Entity)* | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` *(Entity)* | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` *(Entity)* | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` *(Entity)* | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` *(Entity)* | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID` |

---

## inventory

**Script:** `inventory_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `InventoryItemViews`, `InventoryJournalViews`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `inventory_status_enum` | `Active`, `Disabled` | `InventoryItemStatusEnum` | `Active` = 1, `Disabled` = 99 |
| `inventory_type_enum` | `Item`, `Group` | `InventoryTypeEnum` | `Item` = 1, `Group` = 2 |
| `journal_entry_type_enum` | `Dr`, `Cr` | `JournalEntryTypeEnum` | `Dr` = 10, `Cr` = 20 |

---

### Table: `inventory_item_views`

**PostgreSQL Table:** `inventory_item_views`  
**RavenDB Source:** `InventoryItemViews` (C# `InventoryItemView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `group_id` | `GroupId` | `string` (UUID) | `UUID` |
| `inventory_type` | `InventoryType` | `InventoryTypeEnum` | `inventory_type_enum` |
| `uom` | `UOM` | `string` | `VARCHAR(50)` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `attributes` | `Attributes` | `Dictionary<string, object>` | `JSONB` |
| `status` | `Status` | `InventoryItemStatusEnum` | `inventory_status_enum` |

---

### Table: `inventory_journal_views`

**PostgreSQL Table:** `inventory_journal_views`  
**RavenDB Source:** `InventoryJournalViews` (C# `InventoryJournalView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `inventory_item_id` | `InventoryItemId` | `string` (UUID) | `UUID` |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `date` | `Date` | `DateTime` | `TIMESTAMPTZ` |
| `uom` | `UOM` | `string` | `VARCHAR(50)` |
| `quantity` | `Quantity` | `decimal` | `NUMERIC(18, 4)` |
| `rate` | `Rate` | `decimal` | `NUMERIC(18, 2)` |
| `particulars` | `Particulars` | `string` | `TEXT` |
| `reference` | `Reference` | `string` | `VARCHAR(255)` |
| `inventory_journal_id` | `InventoryJournalId` | `string` (UUID) | `UUID` |
| `accounting_journal_id` | `AccountingJournalId` | `string` (UUID) | `UUID` |
| `party_id` | `PartyId` | `string` (UUID) | `UUID` |
| `party_name` | `PartyName` | `string` | `VARCHAR(255)` |
| `journal_entry_type` | `JournalEntryType` | `JournalEntryTypeEnum` | `journal_entry_type_enum` |
| `status` | `Status` | `InventoryJournalStatusEnum` | `inventory_status_enum` |

---

## ledger_account_views

**Script:** `ledger_account_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `LedgerAccountViews`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `ledger_account_status_enum` | `Active`, `Disabled` | `LedgerStatusEnum` | `Active` = 1, `Disabled` = 99 |
| `nature_of_accounts_enum` | `Inherit`, `Assets`, `Liabilities`, `Income`, `Expenses` | `NatureOfAccountsEnum` | `Inherit` = 0, `Assets` = 10, `Liabilities` = 20, `Income` = 30, `Expenses` = 40 |
| `ledger_type_enum` | `Ledger`, `Group` | `LedgerTypeEnum` | `Ledger` = 1, `Group` = 2 |
| `ledger_owner_type_enum` | `Org`, `Inst` | `LedgerOwnerTypeEnum` | `Org` = 1, `Inst` = 2 |

---

### Table: `ledger_account_views`

**PostgreSQL Table:** `ledger_account_views`  
**RavenDB Source:** `LedgerAccountViews` (C# `LedgerAccountView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `group_id` | `GroupId` | `string` (UUID) | `UUID` |
| `group_name` | `GroupName` | `string` | `VARCHAR(255)` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `owner_name` | `OwnerName` | `string` | `VARCHAR(255)` |
| `owner_type` | `OwnerType` | `LedgerOwnerTypeEnum` | `ledger_owner_type_enum` |
| `ledger_type` | `LedgerType` | `LedgerTypeEnum` | `ledger_type_enum` |
| `nature_of_accounts` | `NatureOfAccounts` | `NatureOfAccountsEnum` | `nature_of_accounts_enum` |
| `status` | `Status` | `LedgerStatusEnum` | `ledger_account_status_enum` |

---
## material_views

**Script:** `material_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `MaterialViews`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `material_status_enum` | `Active`, `Reserved`, `Issued`, `UnderMaintenance`, `OutOfCirculation`, `Disabled` | `MaterialStatusEnum` | `Active` = 1, `Reserved` = 5, `Issued` = 10, `UnderMaintenance` = 20, `OutOfCirculation` = 90, `Disabled` = 99 |

---

### Table: `material_views`

**PostgreSQL Table:** `material_views`  
**RavenDB Source:** `MaterialViews` (C# `MaterialView : IReadModelLibrary`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `tracking_id` | `TrackingId` | `string` | `VARCHAR(100)` |
| `isbn` | `ISBN` | `string` | `VARCHAR(100)` |
| `title` | `Title` | `string` | `TEXT` |
| `author` | `Author` | `string` | `VARCHAR(255)` |
| `publisher` | `Publisher` | `string` | `VARCHAR(255)` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `ownership` | `OwnerShip` | `List<Owner>` | `JSONB` |
| `location` | `Location` | `string` | `VARCHAR(255)` |
| `attributes` | `Attributes` | `Dictionary<string, object>` | `JSONB` |
| `tags` | `Tags` | `List<string>` | `TEXT[]` |
| `value` | `Value` | `decimal` | `NUMERIC(18, 2)` |
| `status` | `Status` | `MaterialStatusEnum` | `material_status_enum` |
| `last_verified_on` | `LastVerifiedOn` | `long` | `BIGINT` |
| `pages` | `Pages` | `int` | `INTEGER` |


---

## member_views

**Script:** `member_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `MemberViews`  

### Enums

*None.*

---

### Table: `member_views`

**PostgreSQL Table:** `member_views`  
**RavenDB Source:** `MemberViews` (C# `MemberView : IReadModelLibrary`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `membership_id` | `MembershipId` | `string` | `VARCHAR(100)` |
| `member_type` | `MemberType` | `string` | `VARCHAR(50)` |
| `issued_books` | `IssuedBooks` | `List<string>` | `TEXT[]` |


---

## personas

**Script:** `personas_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Personas`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `persona_type_enum` | `0`, `Anon`, `Management`, `Parent`, `Staff`, `Student`, `External`, `Dev`, `35`, `60`, `70` | `PersonaTypeEnum` | `Anon` = 10, `Management` = 20, `Parent` = 30, `Staff` = 40, `Student` = 50, `External` = 80, `Dev` = 90 |
| `persona_status_enum` | `Unknown`, `Active`, `Disabled` | `PersonaStatusEnum` | `Unknown` = -1, `Active` = 1, `Disabled` = 99 |

---

### Table: `persona`

**PostgreSQL Table:** `persona`  
**RavenDB Source:** `Personas` (C# `Persona : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `title` | `Title` | `string` | `VARCHAR(200)` |
| `display_text` | `DisplayText` | `string` | `VARCHAR(200)` |
| `persona_type` | `PersonaType` | `PersonaTypeEnum` | `persona_type_enum` |
| `persona_type_as_string` | `PersonaTypeAsString` | `string` | `VARCHAR(64)` |
| `scope` | `Scope` | `List<string>` | `TEXT[]` |
| `named_scope` | `NamedScope` | `List<string>` | `TEXT[]` |
| `status` | `Status` | `PersonaStatusEnum` | `persona_status_enum` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |


---
## questions

**Script:** `questions_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `QATags`, `Questions`, `RandomQuestionSubmissions`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `qa_tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |
| `question_status_enum` | `unknown`, `active`, `disabled`, `published`, `wip`, `archived` | `QuestionStatusEnum` | `unknown` = 0, `active` = 1, `disabled` = 99, `published` = 50, `wip` = 40, `archived` = 80 |
| `question_answer_type_enum` | `Text`, `OneOf`, `ManyOf` | `AnswerEnum` | `Text` = 1, `OneOf` = 2, `ManyOf` = 3 |
| `question_difficulty_enum` | `low`, `medium`, `high` | `DifficultyEnum` | `low` = 10, `medium` = 20, `high` = 30 |

---

### Table: `qa_tags`

**PostgreSQL Table:** `qa_tags`  
**RavenDB Source:** `QATags` (C# `QATag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `name` | `Name` | `string` | `VARCHAR(255)` |
| `predefined` | `Predefined` | `bool` | `BOOLEAN` |
| `csn` | `CSN` | `string` | `VARCHAR(50)` |
| `meta` | `Meta` | `Dictionary<string, string>` | `JSONB` |
| `status` | `Status` | `TagStatusEnum` | `qa_tag_status_enum` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |

---

### Table: `questions`

**PostgreSQL Table:** `questions`  
**RavenDB Source:** `Questions` (C# `Question : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `question_text` | `QuestionText` | `string` | `TEXT` |
| `plain_text` | `PlainText` | `string` | `TEXT` |
| `html_text` | `HtmlText` | `string` | `TEXT` |
| `tag_list` | `TagList` | `List<string>` | `TEXT[]` |
| `options` | `Options` | `List<Option>` | `JSONB` |
| `meta` | `Meta` | `Dictionary<string, string>` | `JSONB` |
| `status` | `Status` | `QuestionStatusEnum` | `question_status_enum` |
| `answer_type` | `AnswerType` | `AnswerEnum` | `question_answer_type_enum` |
| `hints` | `Hints` | `List<Hint>` | `JSONB` |
| `instruction` | `Instruction` | `string` | `TEXT` |
| `default_weightage` | `DefaultWeightage` | `decimal` | `NUMERIC(10, 2)` |
| `questions` | `Questions` | `List<SubQuestion>` | `JSONB` |
| `difficulty` | `Difficulty` | `DifficultyEnum` | `question_difficulty_enum` |
| `keywords` | `Keywords` | `List<string>` | `TEXT[]` |
| `isn` | `ISN` | `string` | `VARCHAR(50)` |
| `answer_text` | `AnswerText` | `string` | `TEXT` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |

---

### Table: `random_question_submissions`

**PostgreSQL Table:** `random_question_submissions`  
**RavenDB Source:** `RandomQuestionSubmissions` (C# `RandomQuestionSubmission : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `user_id` | `UserId` | `string` (UUID) | `UUID` |
| `user_email` | `UserEmail` | `string` | `VARCHAR(255)` |
| `questions_answered` | `QuestionsAnswered` | `List<RandomQuestionResult>` | `JSONB` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |

---

## receipts

**Script:** `receipts_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Receipts`  

### Enums

| PostgreSQL Enum Type | Values | C# Enum | C# Values |
|---|---|---|---|
| `receipt_payment_mode_enum` | `Cash`, `Cheque`, `DD`, `Netbanking`, `UPI` | `PaymentModeEnum` | `Cash` = 10, `Cheque` = 20, `DD` = 30, `Netbanking` = 40, `UPI` = 50 |
| `receipt_status_enum` | `Active`, `Cancelled` | `ReceiptStatusEnum` | `Active` = 1, `Cancelled` = 99 |
| `receipt_type_enum` | `Unknown`, `Regular`, `Donation` | `ReceiptTypeEnum` | `Unknown` = 0, `Regular` = 10, `Donation` = 20 |

---

### Table: `receipts`

**PostgreSQL Table:** `receipts`  
**RavenDB Source:** `Receipts` (C# `Receipt : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `number` | `Number` | `string` | `VARCHAR(50)` |
| `inst_id` | `InstId` | `string` (UUID) | `UUID` |
| `date` | `Date` | `DateTime` | `TIMESTAMPTZ` |
| `customer` | `Customer` | `Customer` | `JSONB` |
| `order_items` | `OrderItems` | `List<OrderItem>` | `JSONB` |
| `total_amount` | `TotalAmount` | `decimal` | `NUMERIC(18, 2)` |
| `received_by` | `ReceivedBy` | `string` | `VARCHAR(150)` |
| `payment_mode` | `PaymentMode` | `PaymentModeEnum` | `receipt_payment_mode_enum` |
| `financial_instrument` | `FinancialInstrument` | `FinancialInstrument` | `JSONB` |
| `status` | `Status` | `ReceiptStatusEnum` | `receipt_status_enum` |
| `receipt_type` | `ReceiptType` | `ReceiptTypeEnum` | `receipt_type_enum` |
| `revenue_sharing_enabled` | `RevenueSharingEnabled` | `bool` | `BOOLEAN` |
| `revenue_share` | `RevenueShare` | `int` | `INTEGER` |
| `meta` | `Meta` | `Meta` | `JSONB` |
| `html` | `HTML` | `string` | `TEXT` |
| `ref_no` | `RefNo` | `string` | `VARCHAR(100)` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |

---

## seat_matrices

**Script:** `seat_matrices_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `SeatMatrices`  

### Enums

*None.*

---

### Table: `seat_matrices`

**PostgreSQL Table:** `seat_matrices`  
**RavenDB Source:** `SeatMatrices` (C# `SeatMatrix : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property | C# Type | PostgreSQL Type |
|---|---|---|---|
| `id` | `Id` | `string` (UUID) | `UUID` PRIMARY KEY |
| `course_id` | `CourseId` | `string` (UUID) | `UUID` |
| `course` | `Course` | `string` | `VARCHAR(255)` |
| `total_seats` | `TotalSeats` | `int` | `INTEGER` |
| `break_up` | `BreakUp` | `List<SeatBreakUp>` | `JSONB` |
| `owner_id` | `OwnerId` | `string` (UUID) | `UUID` |
| `parent_id` | `ParentId` | `string` (UUID) | `UUID` |
| `created_on` | `CreatedOn` | `DateTime` | `TIMESTAMPTZ` |
| `created_by` | `CreatedBy` | `string` (UUID) | `UUID` |
| `modified_on` | `ModifiedOn` | `DateTime?` | `TIMESTAMPTZ` |
| `modified_by` | `ModifiedBy` | `string` (UUID) | `UUID` |

---
