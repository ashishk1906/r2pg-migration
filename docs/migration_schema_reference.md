# Migration Schema Reference

---

## Table of Contents

| #  | Script / Domain                                  | RavenDB Collection(s)                              | PostgreSQL Table(s)                                                      |
|:---|:-------------------------------------------------|:---------------------------------------------------|:-------------------------------------------------------------------------|
| 01 | [applications](#01-applications)                 | `ApplicationFormTemplates`, `Applications`         | 01.1 `application_form_templates`<br>01.2 `applications`                 |
| 02 | [artefacts](#02-artefacts)                       | `ArtefactTags`, `Artefacts`                        | 02.1 `artefact_tags`<br>02.2 `artefacts`                                 |
| 03 | [assessments](#03-assessments)                   | `AssessmentTags`, `Assessments`                    | 03.1 `assessment_tags`<br>03.2 `assessments`                             |
| 04 | [asset_views](#04-asset_views)                   | `AssetViews`                                       | 04.1 `asset_views`                                                       |
| 05 | [attendance_events](#05-attendance_events)       | `AttendanceEvents`                                 | 05.1 `attendance_event`                                                  |
| 06 | [calendar_rules](#06-calendar_rules)             | `CalendarRules`                                    | 06.1 `calendar_rules`                                                    |
| 07 | [circulation_views](#07-circulation_views)       | `CirculationViews`                                 | 07.1 `circulation_views`                                                 |
| 08 | [commits](#08-commits)                           | `CommitAssets`, `Commits`, `CommitAcs`             | 08.1 `commit_asset`<br>08.2 `commits`<br>08.3 `commit_ac`                |
| 09 | [content_tags](#09-content_tags)                 | `ContentTags`                                      | 09.1 `content_tags`                                                      |
| 10 | [courses](#10-courses)                           | `Courses`                                          | 10.1 `course`                                                            |
| 11 | [emails](#11-emails)                             | `Emails`                                           | 11.1 `email`                                                             |
| 12 | [exams](#12-exams)                               | `Exams`                                            | 12.1 `exam`                                                              |
| 13 | [fees](#13-fees)                                 | `Fees`, `FeeTxes`                                  | 13.1 `fee`<br>13.2 `fee_transaction`                                     |
| 14 | [gradings](#14-gradings)                         | `Gradings`                                         | 14.1 `gradings`                                                          |
| 15 | [image_tags](#15-image_tags)                     | `ImageTags`                                        | 15.1 `image_tags`                                                        |
| 16 | [institute_calendars](#16-institute_calendars)   | `InstituteCalendars`                               | 16.1 `institute_calendars`                                               |
| 17 | [inventory](#17-inventory)                       | `InventoryItemViews`, `InventoryJournalViews`      | 17.1 `inventory_item_views`<br>17.2 `inventory_journal_views`            |
| 18 | [ledger_account_views](#18-ledger_account_views) | `LedgerAccountViews`                               | 18.1 `ledger_account_views`                                              |
| 19 | [material_views](#19-material_views)             | `MaterialViews`                                    | 19.1 `material_views`                                                    |
| 20 | [member_views](#20-member_views)                 | `MemberViews`                                      | 20.1 `member_views`                                                      |
| 21 | [personas](#21-personas)                         | `Personas`                                         | 21.1 `persona`                                                           |
| 22 | [questions](#22-questions)                       | `QATags`, `Questions`, `RandomQuestionSubmissions` | 22.1 `qa_tags`<br>22.2 `questions`<br>22.3 `random_question_submissions` |
| 23 | [receipts](#23-receipts)                         | `Receipts`                                         | 23.1 `receipts`                                                          |
| 24 | [seat_matrices](#24-seat_matrices)               | `SeatMatrices`                                     | 24.1 `seat_matrices`                                                     |
| 25 | [sms](#25-sms)                                   | `SMs`, `SmsMessages`                               | 25.1 `sms`<br>25.2 `sms_message`                                         |
| 26 | [staffs](#26-staffs)                             | `Staffs`                                           | 26.1 `staffs`                                                            |
| 27 | [students](#27-students)                         | `Orgs`, `Institutes`, `Students`                   | 27.1 `organization`<br>27.2 `institute`<br>27.3 `student`                |
| 28 | [topics](#28-topics)                             | `Topics`                                           | 28.1 `topics`                                                            |
| 29 | [users](#29-users)                               | `Users`                                            | 29.1 `users`                                                             |
| 30 | [voucher_views](#30-voucher_views)               | `VoucherViews`                                     | 30.1 `voucher_views`                                                     |

---

## 01. applications

**Script 01:** `applications_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `ApplicationFormTemplates`, `Applications`  

### Enums

| PostgreSQL Enum Type                    | Values                                                                                                   | C# Enum                             | C# Values                                                                                                         |
|:----------------------------------------|:---------------------------------------------------------------------------------------------------------|:------------------------------------|:------------------------------------------------------------------------------------------------------------------|
| `application_form_template_status_enum` | `Active`, `Published`, `Disabled`                                                                        | `ApplicationFormTemplateStatusEnum` | Active=1, Published=70, Disabled=99                                                                               |
| `residential_status_enum`               | `Indian`, `PIO_OCI`, `NRI`                                                                               | `ResidentialStatusEnum`             | Indian=10, PIO_OCI=20, NRI=30                                                                                     |
| `applicant_category_enum`               | `GM`, `OBC`, `SC`, `ST`                                                                                  | `ApplicantCategoryEnum`             | —                                                                                                                 |
| `applicant_gender_enum`                 | `Female`, `Male`, `NoInfo`                                                                               | `GenderEnum`                        | —                                                                                                                 |
| `application_status_enum`               | `WIP`, `Selected`, `Submitted`, `Shortlisted`, `Admitted`, `Rejected`, `OptedIn`, `OptedOut`, `Declined` | `ApplicationStatusEnum`             | WIP=10, Selected=15, Submitted=20, Shortlisted=25, Admitted=30, Rejected=35, OptedIn=40, OptedOut=45, Declined=50 |

---

### Table 01.1: `application_form_templates`

**PostgreSQL Table:** `application_form_templates`  
**RavenDB Source:** `ApplicationFormTemplates` (C# `ApplicationFormTemplate : Entity`)  
**Primary Key:** `id` (`UUID` PRIMARY KEY)  

| PostgreSQL Column | C# Property             | C# Type                             | PostgreSQL Type                         |
|:------------------|:------------------------|:------------------------------------|:----------------------------------------|
| `id`              | `Id`                    | `string` (UUID)                     | `UUID PRIMARY KEY`                      |
| `title`           | `Title`                 | `string`                            | `VARCHAR(255)`                          |
| `description`     | `Description`           | `string`                            | `TEXT`                                  |
| `options`         | `Options`               | `AdmissionFormOptions` (object)     | `JSONB`                                 |
| `start_date`      | `StartDate`             | `DateTime`                          | `TIMESTAMPTZ`                           |
| `end_date`        | `EndDate`               | `DateTime`                          | `TIMESTAMPTZ`                           |
| `status`          | `Status`                | `ApplicationFormTemplateStatusEnum` | `application_form_template_status_enum` |
| `shortlists`      | `Shortlists`            | `List<Shortlist>`                   | `JSONB`                                 |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)                     | `UUID`                                  |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)                     | `UUID`                                  |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                          | `TIMESTAMPTZ`                           |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)                     | `UUID`                                  |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                         | `TIMESTAMPTZ`                           |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)                     | `UUID`                                  |

---

### Table 01.2: `applications`

**PostgreSQL Table:** `applications`  
**RavenDB Source:** `Applications` (C# `Application : Entity`)  
**Primary Key:** `id` (`UUID` PRIMARY KEY)  

| PostgreSQL Column              | C# Property                 | C# Type                     | PostgreSQL Type           |
|:-------------------------------|:----------------------------|:----------------------------|:--------------------------|
| `id`                           | `Id`                        | `string` (UUID)             | `UUID PRIMARY KEY`        |
| `name`                         | `Name`                      | `string`                    | `VARCHAR(255)`            |
| `email`                        | `Email`                     | `string`                    | `VARCHAR(255)`            |
| `mobile`                       | `Mobile`                    | `string`                    | `VARCHAR(50)`             |
| `dob`                          | `DOB`                       | `DateTime`                  | `TIMESTAMPTZ`             |
| `residential_status`           | `ResidentialStatus`         | `ResidentialStatusEnum`     | `residential_status_enum` |
| `category`                     | `Category`                  | `ApplicantCategoryEnum`     | `applicant_category_enum` |
| `gender`                       | `Gender`                    | `GenderEnum`                | `applicant_gender_enum`   |
| `address`                      | `Address`                   | `ApplicantAddress` (object) | `JSONB`                   |
| `hsc`                          | `HSC`                       | `AcademicHistory` (object)  | `JSONB`                   |
| `ssc`                          | `SSC`                       | `AcademicHistory` (object)  | `JSONB`                   |
| `father_details`               | `FatherDetails`             | `ParentDetails` (object)    | `JSONB`                   |
| `mother_details`               | `MotherDetails`             | `ParentDetails` (object)    | `JSONB`                   |
| `guardian_details`             | `GuardianDetails`           | `ParentDetails` (object)    | `JSONB`                   |
| `applied_for`                  | `AppliedFor`                | `AppliedFor` (object)       | `JSONB`                   |
| `payment`                      | `Payment`                   | `Payment` (object)          | `JSONB`                   |
| `photo_url`                    | `PhotoURL`                  | `string`                    | `TEXT`                    |
| `aadhar_url`                   | `AadharURL`                 | `string`                    | `TEXT`                    |
| `hsc_marks_card_url`           | `HSCMarksCardURL`           | `string`                    | `TEXT`                    |
| `ssc_marks_card_url`           | `SSCMarksCardURL`           | `string`                    | `TEXT`                    |
| `caste_certificate_url`        | `CasteCertificateURL`       | `string`                    | `TEXT`                    |
| `domicile_certificate_url`     | `DomicileCertificateURL`    | `string`                    | `TEXT`                    |
| `birth_certificate_url`        | `BirthCertificateURL`       | `string`                    | `TEXT`                    |
| `transfer_certificate_url`     | `TransferCertificateURL`    | `string`                    | `TEXT`                    |
| `leaving_certificate_url`      | `LeavingCertificateURL`     | `string`                    | `TEXT`                    |
| `application_form_template_id` | `ApplicationFormTemplateId` | `string` (UUID)             | `UUID`                    |
| `submitted_on`                 | `SubmittedOn`               | `DateTime`                  | `TIMESTAMPTZ`             |
| `application_number`           | `ApplicationNumber`         | `int`                       | `INTEGER`                 |
| `shortlisted_in`               | `ShortlistedIn`             | `int`                       | `INTEGER`                 |
| `doa`                          | `DOA`                       | `DateTime`                  | `TIMESTAMPTZ`             |
| `application_status`           | `ApplicationStatus`         | `ApplicationStatusEnum`     | `application_status_enum` |
| `owner_id`                     | `OwnerId` *(Entity)*        | `string` (UUID)             | `UUID`                    |
| `parent_id`                    | `ParentId` *(Entity)*       | `string` (UUID)             | `UUID`                    |
| `created_on`                   | `CreatedOn` *(Entity)*      | `DateTime`                  | `TIMESTAMPTZ`             |
| `created_by`                   | `CreatedBy` *(Entity)*      | `string` (UUID)             | `UUID`                    |
| `modified_on`                  | `ModifiedOn` *(Entity)*     | `DateTime?`                 | `TIMESTAMPTZ`             |
| `modified_by`                  | `ModifiedBy` *(Entity)*     | `string` (UUID)             | `UUID`                    |

---

## 02. artefacts

**Script 02:** `artefacts_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `ArtefactTags`, `Artefacts`  

### Enums

| PostgreSQL Enum Type   | Values                                                                                             | C# Enum              | C# Values                                                                                                                                |
|:-----------------------|:---------------------------------------------------------------------------------------------------|:---------------------|:-----------------------------------------------------------------------------------------------------------------------------------------|
| `tag_status_enum`      | `Unknown`, `Active`, `Disabled`                                                                    | `TagStatusEnum`      | `Unknown` = 0, `Active` = 1, `Disabled` = 99                                                                                             |
| `artefact_status_enum` | `Unknown`, `Active`, `Etl`, `Published`, `PublishedToPublic`, `Uploaded`, `Downloaded`, `Disabled` | `ArtefactStatusEnum` | `Unknown` = 0, `Active` = 1, `Etl` = 60, `Published` = 70, `PublishedToPublic` = 75, `Uploaded` = 80, `Downloaded` = 90, `Disabled` = 99 |

---

### Table 02.1: `artefact_tags`

**PostgreSQL Table:** `artefact_tags`  
**RavenDB Source:** `ArtefactTags` (Entity: `ArtefactTag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type                      | PostgreSQL Type    |
|:------------------|:------------------------|:-----------------------------|:-------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)              | `UUID` PRIMARY KEY |
| `name`            | `Name`                  | `string`                     | `VARCHAR(150)`     |
| `predefined`      | `Predefined`            | `bool`                       | `BOOLEAN`          |
| `csn`             | `CSN`                   | `string`                     | `VARCHAR(100)`     |
| `meta`            | `Meta`                  | `Dictionary<string, string>` | `JSONB`            |
| `status`          | `Status`                | `TagStatusEnum`              | `tag_status_enum`  |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)              | `UUID`             |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)              | `UUID`             |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                   | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)              | `UUID`             |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                  | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)              | `UUID`             |

---

### Table 02.2: `artefacts`

**PostgreSQL Table:** `artefacts`  
**RavenDB Source:** `Artefacts` (Entity: `Artefact : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type                      | PostgreSQL Type        |
|:------------------|:------------------------|:-----------------------------|:-----------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)              | `UUID` PRIMARY KEY     |
| `url`             | `Url`                   | `string`                     | `TEXT`                 |
| `title`           | `Title`                 | `string`                     | `VARCHAR(250)`         |
| `description`     | `Description`           | `string`                     | `TEXT`                 |
| `meta_data`       | `MetaData`              | `Dictionary<string, string>` | `JSONB`                |
| `tags`            | `Tags`                  | `List<string>`               | `TEXT[]`               |
| `mime_type`       | `MimeType`              | `string`                     | `VARCHAR(100)`         |
| `file_name`       | `FileName`              | `string`                     | `VARCHAR(250)`         |
| `file_size`       | `FileSize`              | `double`                     | `DOUBLE PRECISION`     |
| `status`          | `Status`                | `ArtefactStatusEnum`         | `artefact_status_enum` |
| `sha1`            | `SHA1`                  | `string`                     | `VARCHAR(100)`         |
| `model`           | `Model`                 | `string`                     | `TEXT`                 |
| `template`        | `Template`              | `string`                     | `TEXT`                 |
| `csv`             | `Csv`                   | `string`                     | `TEXT`                 |
| `change_set`      | `ChangeSet`             | `List<ChangeRef>`            | `JSONB`                |
| `comments`        | `Comments`              | `List<Comment>`              | `JSONB`                |
| `video_links`     | `VideoLinks`            | `List<VideoLink>`            | `JSONB`                |
| `data_attributes` | `DataAttributes`        | `List<DataAttribute>`        | `JSONB`                |
| `published_on`    | `PublishedOn`           | `DateTime`                   | `TIMESTAMPTZ`          |
| `public_urls`     | `PublicUrls`            | `List<string>`               | `TEXT[]`               |
| `thumbnails`      | `Thumbnails`            | `List<string>`               | `TEXT[]`               |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)              | `UUID`                 |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)              | `UUID`                 |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                   | `TIMESTAMPTZ`          |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)              | `UUID`                 |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                  | `TIMESTAMPTZ`          |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)              | `UUID`                 |

---

## 03. assessments

**Script 03:** `assessments_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `AssessmentTags`, `Assessments`  

### Enums

| PostgreSQL Enum Type     | Values                                                          | C# Enum                | C# Values                                                                                   |
|:-------------------------|:----------------------------------------------------------------|:-----------------------|:--------------------------------------------------------------------------------------------|
| `tag_status_enum`        | `Unknown`, `Active`, `Disabled`                                 | `TagStatusEnum`        | `Unknown` = 0, `Active` = 1, `Disabled` = 99                                                |
| `assessment_status_enum` | `Unknown`, `Active`, `WIP`, `Published`, `Archived`, `Disabled` | `AssessmentStatusEnum` | `Unknown` = 0, `Active` = 1, `WIP` = 40, `Published` = 50, `Archived` = 80, `Disabled` = 99 |

---

### Table 03.1: `assessment_tags`

**PostgreSQL Table:** `assessment_tags`  
**RavenDB Source:** `AssessmentTags` (Entity: `AssessmentTag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type                      | PostgreSQL Type    |
|:------------------|:------------------------|:-----------------------------|:-------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)              | `UUID` PRIMARY KEY |
| `name`            | `Name`                  | `string`                     | `VARCHAR(150)`     |
| `predefined`      | `Predefined`            | `bool`                       | `BOOLEAN`          |
| `csn`             | `CSN`                   | `string`                     | `VARCHAR(100)`     |
| `meta`            | `Meta`                  | `Dictionary<string, string>` | `JSONB`            |
| `status`          | `Status`                | `TagStatusEnum`              | `tag_status_enum`  |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)              | `UUID`             |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)              | `UUID`             |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                   | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)              | `UUID`             |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                  | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)              | `UUID`             |

---

### Table 03.2: `assessments`

**PostgreSQL Table:** `assessments`  
**RavenDB Source:** `Assessments` (Entity: `Assessment : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column   | C# Property             | C# Type                   | PostgreSQL Type          |
|:--------------------|:------------------------|:--------------------------|:-------------------------|
| `id`                | `Id` *(Entity)*         | `string` (UUID)           | `UUID` PRIMARY KEY       |
| `total_marks`       | `TotalMarks`            | `decimal`                 | `NUMERIC(14, 2)`         |
| `description`       | `Description`           | `string`                  | `TEXT`                   |
| `subject`           | `Subject`               | `string`                  | `VARCHAR(150)`           |
| `subject_code`      | `SubjectCode`           | `string`                  | `VARCHAR(50)`            |
| `duration`          | `Duration`              | `int`                     | `INT`                    |
| `sections`          | `Sections`              | `List<AssessmentSection>` | `JSONB`                  |
| `status`            | `Status`                | `AssessmentStatusEnum`    | `assessment_status_enum` |
| `multiple_attempts` | `MultipleAttempts`      | `bool`                    | `BOOLEAN`                |
| `tags`              | `Tags`                  | `List<string>`            | `TEXT[]`                 |
| `owner_id`          | `OwnerId` *(Entity)*    | `string` (UUID)           | `UUID`                   |
| `parent_id`         | `ParentId` *(Entity)*   | `string` (UUID)           | `UUID`                   |
| `created_on`        | `CreatedOn` *(Entity)*  | `DateTime`                | `TIMESTAMPTZ`            |
| `created_by`        | `CreatedBy` *(Entity)*  | `string` (UUID)           | `UUID`                   |
| `modified_on`       | `ModifiedOn` *(Entity)* | `DateTime?`               | `TIMESTAMPTZ`            |
| `modified_by`       | `ModifiedBy` *(Entity)* | `string` (UUID)           | `UUID`                   |

---

## 04. asset_views

**Script 04:** `asset_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `AssetViews`  

### Enums

| PostgreSQL Enum Type | Values                          | C# Enum           | C# Values                                     |
|:---------------------|:--------------------------------|:------------------|:----------------------------------------------|
| `asset_status_enum`  | `Active`, `Cleared`, `Disabled` | `AssetStatusEnum` | `Active` = 1, `Cleared` = 90, `Disabled` = 99 |

---

### Table 04.1: `asset_views`

**PostgreSQL Table:** `asset_views`  
**RavenDB Source:** `AssetViews` (C# `AssetView : IReadModelAssets`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column  | C# Property       | C# Type           | PostgreSQL Type     |
|:-------------------|:------------------|:------------------|:--------------------|
| `id`               | `Id`              | `string` (UUID)   | `UUID` PRIMARY KEY  |
| `tracking_id`      | `TrackingId`      | `string`          | `VARCHAR(100)`      |
| `owner_id`         | `OwnerId`         | `string` (UUID)   | `UUID`              |
| `location`         | `Location`        | `string`          | `VARCHAR(250)`      |
| `attributes`       | `Attributes`      | `string` (JSON)   | `JSONB`             |
| `tags`             | `Tags`            | `List<string>`    | `TEXT[]`            |
| `value`            | `Value`           | `decimal`         | `NUMERIC(18, 2)`    |
| `last_maintenance` | `LastMaintenance` | `Maintenance`     | `JSONB`             |
| `current_warranty` | `CurrentWarranty` | `Warranty`        | `JSONB`             |
| `status`           | `Status`          | `AssetStatusEnum` | `asset_status_enum` |
| `under_warranty`   | `UnderWarranty`   | `bool`            | `BOOLEAN`           |

---

## 05. attendance_events

**Script 05:** `attendance_events_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `AttendanceEvents`  

### Enums

*No custom enum types defined for this domain.*

---

### Table 05.1: `attendance_event`

**PostgreSQL Table:** `attendance_event`  
**RavenDB Source:** `AttendanceEvents` (C# `AttendanceEvent : Entity`)  
**Primary Key:** `id` (`VARCHAR(100)`)  

| PostgreSQL Column     | C# Property             | C# Type         | PostgreSQL Type            |
|:----------------------|:------------------------|:----------------|:---------------------------|
| `id`                  | `Id`                    | `string`        | `VARCHAR(100)` PRIMARY KEY |
| `inst_id`             | `InstId`                | `string` (UUID) | `UUID`                     |
| `course_id`           | `CourseId`              | `string` (UUID) | `UUID`                     |
| `term_name`           | `TermName`              | `string`        | `VARCHAR(100)`             |
| `section_name`        | `SectionName`           | `string`        | `VARCHAR(50)`              |
| `date`                | `Date`                  | `DateTime`      | `TIMESTAMPTZ`              |
| `period_no`           | `PeriodNo`              | `int`           | `INTEGER`                  |
| `subject_name`        | `SubjectName`           | `string`        | `VARCHAR(200)`             |
| `is_optional_subject` | `IsOptionalSubject`     | `bool`          | `BOOLEAN`                  |
| `student_id`          | `StudentId`             | `string` (UUID) | `UUID`                     |
| `staff_id`            | `StaffId`               | `string`        | `VARCHAR(100)`             |
| `attendance`          | `Attendance`            | `string`        | `VARCHAR(50)`              |
| `created_on`          | `CreatedOn` *(Entity)*  | `DateTime`      | `TIMESTAMPTZ`              |
| `created_by`          | `CreatedBy` *(Entity)*  | `string` (UUID) | `UUID`                     |
| `owner_id`            | `OwnerId` *(Entity)*    | `string` (UUID) | `UUID`                     |
| `parent_id`           | `ParentId` *(Entity)*   | `string` (UUID) | `UUID`                     |
| `modified_on`         | `ModifiedOn` *(Entity)* | `DateTime?`     | `TIMESTAMPTZ`              |
| `modified_by`         | `ModifiedBy` *(Entity)* | `string` (UUID) | `UUID`                     |

---

## 06. calendar_rules

**Script 06:** `calendar_rules_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `CalendarRules`  

### Enums

| PostgreSQL Enum Type           | Values                                      | C# Enum                     | C# Values                                                       |
|:-------------------------------|:--------------------------------------------|:----------------------------|:----------------------------------------------------------------|
| `calendar_rule_status_enum`    | `Active`, `Disabled`                        | `CalendarRuleStatusEnum`    | `Active` = 1, `Disabled` = 99                                   |
| `calendar_event_category_enum` | `Event`, `Holiday`, `WeeklyHoliday`, `Exam` | `CalendarEventCategoryEnum` | `Event` = 10, `Holiday` = 20, `WeeklyHoliday` = 30, `Exam` = 40 |

---

### Table 06.1: `calendar_rules`

**PostgreSQL Table:** `calendar_rules`  
**RavenDB Source:** `CalendarRules` (C# `CalendarRule : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column         | C# Property             | C# Type                     | PostgreSQL Type                |
|:--------------------------|:------------------------|:----------------------------|:-------------------------------|
| `id`                      | `Id` *(Entity)*         | `string` (UUID)             | `UUID` PRIMARY KEY             |
| `title`                   | `Title`                 | `string`                    | `VARCHAR(255)`                 |
| `cron_expression`         | `CronExpression`        | `string`                    | `VARCHAR(100)`                 |
| `calendar_rule_status`    | `CalendarRuleStatus`    | `CalendarRuleStatusEnum`    | `calendar_rule_status_enum`    |
| `calendar_event_category` | `CalendarEventCategory` | `CalendarEventCategoryEnum` | `calendar_event_category_enum` |
| `weight`                  | `Weight`                | `int`                       | `INTEGER`                      |
| `duration`                | `Duration`              | `decimal`                   | `NUMERIC(10, 2)`               |
| `topic_id`                | `TopicId`               | `string` (UUID)             | `UUID`                         |
| `user_id`                 | `UserId`                | `string` (UUID)             | `UUID`                         |
| `create_meeting_link`     | `CreateMeetingLink`     | `bool`                      | `BOOLEAN`                      |
| `owner_id`                | `OwnerId` *(Entity)*    | `string` (UUID)             | `UUID`                         |
| `parent_id`               | `ParentId` *(Entity)*   | `string` (UUID)             | `UUID`                         |
| `created_on`              | `CreatedOn` *(Entity)*  | `DateTime`                  | `TIMESTAMPTZ`                  |
| `created_by`              | `CreatedBy` *(Entity)*  | `string` (UUID)             | `UUID`                         |
| `modified_on`             | `ModifiedOn` *(Entity)* | `DateTime?`                 | `TIMESTAMPTZ`                  |
| `modified_by`             | `ModifiedBy` *(Entity)* | `string` (UUID)             | `UUID`                         |

---

## 07. circulation_views

**Script 07:** `circulation_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `CirculationViews`  

### Enums

*No custom enum types defined for this domain.*

---

### Table 07.1: `circulation_views`

**PostgreSQL Table:** `circulation_views`  
**RavenDB Source:** `CirculationViews` (C# `CirculationView : IReadModelLibrary`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property  | C# Type         | PostgreSQL Type    |
|:------------------|:-------------|:----------------|:-------------------|
| `id`              | `Id`         | `string` (UUID) | `UUID` PRIMARY KEY |
| `owner_id`        | `OwnerId`    | `string` (UUID) | `UUID`             |
| `tracking_id`     | `TrackingId` | `string`        | `VARCHAR(100)`     |
| `issued_on`       | `IssuedOn`   | `DateTime`      | `TIMESTAMPTZ`      |
| `received_on`     | `ReceivedOn` | `DateTime`      | `TIMESTAMPTZ`      |
| `due_on`          | `DueOn`      | `DateTime`      | `TIMESTAMPTZ`      |
| `reissued_on`     | `ReissuedOn` | `DateTime`      | `TIMESTAMPTZ`      |
| `issued_to`       | `IssuedTo`   | `string`        | `VARCHAR(100)`     |

---

## 08. commits

**Script 08:** `commits_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `CommitAssets`, `Commits`, `CommitAcs`  

### Enums

*No custom enum types defined for this domain.*

---

### Tables 08.1 - 08.3: `commit_asset`, `commits`, `commit_ac`

**PostgreSQL Tables:** `commit_asset`, `commits`, `commit_ac`  
**RavenDB Sources:**  
- `commit_asset` $\leftarrow$ `CommitAssets` (C# `CommitAssets`)
- `commits` $\leftarrow$ `Commits` (C# `Commit`)
- `commit_ac` $\leftarrow$ `CommitAcs` (C# `CommitAc`)
**Primary Key:** `id` (`UUID`)  
All three tables share the same Common Commit Wrapper schema:  

| PostgreSQL Column | C# Property    | C# Type         | PostgreSQL Type    |
|:------------------|:---------------|:----------------|:-------------------|
| `id`              | `Id`           | `string` (UUID) | `UUID` PRIMARY KEY |
| `aggregate_id`    | `AggregateId`  | `string` (UUID) | `UUID`             |
| `version`         | `Version`      | `int`           | `INTEGER`          |
| `user_id`         | `UserId`       | `string` (UUID) | `UUID`             |
| `inst_id`         | `InstId`       | `string` (UUID) | `UUID`             |
| `timestamp`       | `TimeStamp`    | `DateTime`      | `TIMESTAMPTZ`      |
| `event_message`   | `EventMessage` | `object`        | `JSONB`            |

---

## 09. content_tags

**Script 09:** `content_tags_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `ContentTags`  

### Enums

| PostgreSQL Enum Type      | Values                          | C# Enum         | C# Values                                    |
|:--------------------------|:--------------------------------|:----------------|:---------------------------------------------|
| `content_tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table 09.1: `content_tags`

**PostgreSQL Table:** `content_tags`  
**RavenDB Source:** `ContentTags` (C# `ContentTag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type                      | PostgreSQL Type           |
|:------------------|:------------------------|:-----------------------------|:--------------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)              | `UUID` PRIMARY KEY        |
| `name`            | `Name`                  | `string`                     | `VARCHAR(255)`            |
| `predefined`      | `Predefined`            | `bool`                       | `BOOLEAN`                 |
| `csn`             | `CSN`                   | `string`                     | `VARCHAR(50)`             |
| `meta`            | `Meta`                  | `Dictionary<string, string>` | `JSONB`                   |
| `status`          | `Status`                | `TagStatusEnum`              | `content_tag_status_enum` |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)              | `UUID`                    |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)              | `UUID`                    |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                   | `TIMESTAMPTZ`             |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)              | `UUID`                    |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                  | `TIMESTAMPTZ`             |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)              | `UUID`                    |

---

## 10. courses

**Script 10:** `courses_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Courses`  

### Enums

| PostgreSQL Enum Type | Values                                                                                    | C# Enum            | C# Values                                                                                                                  |
|:---------------------|:------------------------------------------------------------------------------------------|:-------------------|:---------------------------------------------------------------------------------------------------------------------------|
| `edu_level_enum`     | `Unknown`, `PreNursery`, `Nursery`, `School`, `UnderGraduate`, `Graduate`, `PostGraduate` | `EduLevelEnum`     | `Unknown` = -1, `PreNursery` = 2, `Nursery` = 5, `School` = 10, `UnderGraduate` = 20, `Graduate` = 30, `PostGraduate` = 40 |
| `course_status_enum` | `Unknown`, `Active`, `Disabled`                                                           | `CourseStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99                                                                               |

---

### Table 10.1: `course`

**PostgreSQL Table:** `course`  
**RavenDB Source:** `Courses` (C# `Course : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column     | C# Property             | C# Type            | PostgreSQL Type      |
|:----------------------|:------------------------|:-------------------|:---------------------|
| `id`                  | `Id` *(Entity)*         | `string` (UUID)    | `UUID` PRIMARY KEY   |
| `name`                | `Name`                  | `string`           | `VARCHAR(200)`       |
| `branch`              | `Branch`                | `string`           | `VARCHAR(100)`       |
| `name_and_branch`     | `NameAndBranch`         | `string`           | `VARCHAR(200)`       |
| `edu_level`           | `EduLevel`              | `EduLevelEnum`     | `edu_level_enum`     |
| `edu_level_as_string` | `EduLevelAsString`      | `string`           | `VARCHAR(32)`        |
| `inst_id`             | `InstId`                | `string` (UUID)    | `UUID`               |
| `affiliation`         | `Affiliation`           | `string`           | `VARCHAR(100)`       |
| `status`              | `Status`                | `CourseStatusEnum` | `course_status_enum` |
| `status_as_string`    | `StatusAsString`        | `string`           | `VARCHAR(32)`        |
| `terms`               | `Terms`                 | `List<Term>`       | `JSONB`              |
| `exam_subject_order`  | `ExamSubjectOrder`      | `List<string>`     | `TEXT[]`             |
| `sort_index`          | `SortIndex`             | `int`              | `INTEGER`            |
| `rank`                | `Rank`                  | `int`              | `INTEGER`            |
| `seats_available`     | `SeatsAvailable`        | `int`              | `INTEGER`            |
| `program`             | `Program`               | `string`           | `TEXT`               |
| `owner_id`            | `OwnerId` *(Entity)*    | `string` (UUID)    | `UUID`               |
| `parent_id`           | `ParentId` *(Entity)*   | `string` (UUID)    | `UUID`               |
| `created_on`          | `CreatedOn` *(Entity)*  | `DateTime`         | `TIMESTAMPTZ`        |
| `created_by`          | `CreatedBy` *(Entity)*  | `string` (UUID)    | `UUID`               |
| `modified_on`         | `ModifiedOn` *(Entity)* | `DateTime?`        | `TIMESTAMPTZ`        |
| `modified_by`         | `ModifiedBy` *(Entity)* | `string` (UUID)    | `UUID`               |

---

## 11. emails

**Script 11:** `emails_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Emails`  

### Enums

*No custom enum types defined for this domain.*

---

### Table 11.1: `email`

**PostgreSQL Table:** `email`  
**RavenDB Source:** `Emails` (C# `Email : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type            | PostgreSQL Type    |
|:------------------|:------------------------|:-------------------|:-------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)    | `UUID` PRIMARY KEY |
| `recipients`      | `Recipients`            | `List<string>`     | `TEXT[]`           |
| `message`         | `Message`               | `string`           | `TEXT`             |
| `type`            | `Type`                  | `string`           | `VARCHAR(50)`      |
| `from`            | `From`                  | `string`           | `VARCHAR(255)`     |
| `subject`         | `Subject`               | `string`           | `VARCHAR(500)`     |
| `attachments`     | `Attachments`           | `List<Attachment>` | `JSONB`            |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)    | `UUID`             |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)    | `UUID`             |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`         | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)    | `UUID`             |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`        | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)    | `UUID`             |

---

## 12. exams

**Script 12:** `exams_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Exams`  

### Enums

| PostgreSQL Enum Type | Values                                                              | C# Enum          | C# Values                                                                                       |
|:---------------------|:--------------------------------------------------------------------|:-----------------|:------------------------------------------------------------------------------------------------|
| `exam_status_enum`   | `Unknown`, `Active`, `Scheduled`, `Conducted`, `Locked`, `Disabled` | `ExamStatusEnum` | `Unknown` = 0, `Active` = 1, `Scheduled` = 10, `Conducted` = 20, `Locked` = 90, `Disabled` = 99 |

---

### Table 12.1: `exam`

**PostgreSQL Table:** `exam`  
**RavenDB Source:** `Exams` (C# `Exam : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type             | PostgreSQL Type    |
|:------------------|:------------------------|:--------------------|:-------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)     | `UUID` PRIMARY KEY |
| `name`            | `Name`                  | `string`            | `VARCHAR(200)`     |
| `inst_id`         | `InstId`                | `string` (UUID)     | `UUID`             |
| `course_id`       | `CourseId`              | `string` (UUID)     | `UUID`             |
| `term`            | `Term`                  | `string`            | `VARCHAR(64)`      |
| `section`         | `Section`               | `string`            | `VARCHAR(32)`      |
| `exam_contents`   | `ExamContents`          | `List<ExamContent>` | `JSONB`            |
| `lock_history`    | `LockHistory`           | `List<LockEntry>`   | `JSONB`            |
| `attendance_list` | `AttendanceList`        | `List<Attendance>`  | `JSONB`            |
| `remarks_list`    | `RemarksList`           | `List<Remark>`      | `JSONB`            |
| `status`          | `Status`                | `ExamStatusEnum`    | `exam_status_enum` |
| `days_worked`     | `DaysWorked`            | `int`               | `INTEGER`          |
| `total_max_marks` | `TotalMaxMarks`         | `decimal`           | `NUMERIC(14, 2)`   |
| `merge_index`     | `MergeIndex`            | `int`               | `INTEGER`          |
| `start_date`      | `StartDate`             | `DateTime`          | `TIMESTAMPTZ`      |
| `result_date`     | `ResultDate`            | `DateTime`          | `TIMESTAMPTZ`      |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)     | `UUID`             |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)     | `UUID`             |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`          | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)     | `UUID`             |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`         | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)     | `UUID`             |

---

## 13. fees

**Script 13:** `fees_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `Fees`, `FeeTxes`  

### Enums

| PostgreSQL Enum Type | Values                          | C# Enum           | C# Values                                    |
|:---------------------|:--------------------------------|:------------------|:---------------------------------------------|
| `fee_status_enum`    | `Unknown`, `Active`, `Disabled` | `FeeStatusEnum`   | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |
| `fee_tx_status_enum` | `Active`, `Disabled`            | `FeeTxStatusEnum` | `Active` = 1, `Disabled` = 99                |

---

### Table 13.1: `fee`

**PostgreSQL Table:** `fee`  
**RavenDB Source:** `Fees` (C# `Fee : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column      | C# Property             | C# Type             | PostgreSQL Type    |
|:-----------------------|:------------------------|:--------------------|:-------------------|
| `id`                   | `Id` *(Entity)*         | `string` (UUID)     | `UUID` PRIMARY KEY |
| `name`                 | `Name`                  | `string`            | `VARCHAR(200)`     |
| `name_lower`           | `NameLower`             | `string`            | `VARCHAR(200)`     |
| `display_text`         | `DisplayText`           | `string`            | `VARCHAR(200)`     |
| `amount`               | `Amount`                | `decimal`           | `NUMERIC(14, 2)`   |
| `tags`                 | `Tags`                  | `List<string>`      | `TEXT[]`           |
| `collect_student_wise` | `CollectStudentWise`    | `bool`              | `BOOLEAN`          |
| `student_list`         | `StudentList`           | `List<string>`      | `TEXT[]`           |
| `course_list`          | `CourseList`            | `List<string>`      | `TEXT[]`           |
| `installments`         | `Installments`          | `List<Installment>` | `JSONB`            |
| `fines`                | `Fines`                 | `List<Fine>`        | `JSONB`            |
| `is_tx_done`           | `IsTxDone`              | `bool`              | `BOOLEAN`          |
| `status`               | `Status`                | `FeeStatusEnum`     | `fee_status_enum`  |
| `owner_id`             | `OwnerId` *(Entity)*    | `string` (UUID)     | `UUID`             |
| `parent_id`            | `ParentId` *(Entity)*   | `string` (UUID)     | `UUID`             |
| `created_on`           | `CreatedOn` *(Entity)*  | `DateTime`          | `TIMESTAMPTZ`      |
| `created_by`           | `CreatedBy` *(Entity)*  | `string` (UUID)     | `UUID`             |
| `modified_on`          | `ModifiedOn` *(Entity)* | `DateTime?`         | `TIMESTAMPTZ`      |
| `modified_by`          | `ModifiedBy` *(Entity)* | `string` (UUID)     | `UUID`             |

---

### Table 13.2: `fee_transaction`

**PostgreSQL Table:** `fee_transaction`  
**RavenDB Source:** `FeeTxes` (C# `FeeTx : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column             | C# Property                | C# Type                | PostgreSQL Type      |
|:------------------------------|:---------------------------|:-----------------------|:---------------------|
| `id`                          | `Id` *(Entity)*            | `string` (UUID)        | `UUID` PRIMARY KEY   |
| `tx_no`                       | `TxNo`                     | `string`               | `VARCHAR(100)`       |
| `tx_date`                     | `TxDate`                   | `DateTime`             | `TIMESTAMPTZ`        |
| `student_id`                  | `StudentId`                | `string` (UUID)        | `UUID`               |
| `installments_paid`           | `InstallmentsPaid`         | `List<FeeTxDto>`       | `JSONB`              |
| `fines_paid`                  | `FinesPaid`                | `List<FeeFineDto>`     | `JSONB`              |
| `discounts`                   | `Discounts`                | `List<FeeDiscountDto>` | `JSONB`              |
| `fee_adjustment`              | `FeeAdjustment`            | `FeeAdjustmentDto`     | `JSONB`              |
| `payment_mode`                | `PaymentMode`              | `string`               | `VARCHAR(64)`        |
| `is_fine_paid`                | `IsFinePaid`               | `bool`                 | `BOOLEAN`            |
| `is_discount_given`           | `IsDiscountGiven`          | `bool`                 | `BOOLEAN`            |
| `has_fee_adjustment`          | `HasFeeAdjustment`         | `bool`                 | `BOOLEAN`            |
| `is_opening_balance_adjusted` | `IsOpeningBalanceAdjusted` | `bool`                 | `BOOLEAN`            |
| `ref_no`                      | `RefNo`                    | `string`               | `VARCHAR(100)`       |
| `amount`                      | `Amount`                   | `decimal`              | `NUMERIC(14, 2)`     |
| `status`                      | `Status`                   | `FeeTxStatusEnum`      | `fee_tx_status_enum` |
| `paid_by`                     | `PaidBy`                   | `string`               | `VARCHAR(100)`       |
| `cheque_no`                   | `ChequeNo`                 | `string`               | `VARCHAR(100)`       |
| `bank_name`                   | `BankName`                 | `string`               | `VARCHAR(200)`       |
| `cheque_date`                 | `ChequeDate`               | `DateTime`             | `TIMESTAMPTZ`        |
| `online_txn_ref_no`           | `OnlineTxnRefNo`           | `string`               | `VARCHAR(100)`       |
| `owner_id`                    | `OwnerId` *(Entity)*       | `string` (UUID)        | `UUID`               |
| `parent_id`                   | `ParentId` *(Entity)*      | `string` (UUID)        | `UUID`               |
| `created_on`                  | `CreatedOn` *(Entity)*     | `DateTime`             | `TIMESTAMPTZ`        |
| `created_by`                  | `CreatedBy` *(Entity)*     | `string` (UUID)        | `UUID`               |
| `modified_on`                 | `ModifiedOn` *(Entity)*    | `DateTime?`            | `TIMESTAMPTZ`        |
| `modified_by`                 | `ModifiedBy` *(Entity)*    | `string` (UUID)        | `UUID`               |

---

## 14. gradings

**Script 14:** `gradings_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Gradings`  

### Enums

| PostgreSQL Enum Type  | Values               | C# Enum             | C# Values                     |
|:----------------------|:---------------------|:--------------------|:------------------------------|
| `grading_status_enum` | `Active`, `Disabled` | `GradingStatusEnum` | `Active` = 1, `Disabled` = 99 |

---

### Table 14.1: `gradings`

**PostgreSQL Table:** `gradings`  
**RavenDB Source:** `Gradings` (C# `Grading : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type             | PostgreSQL Type       |
|:------------------|:------------------------|:--------------------|:----------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)     | `UUID` PRIMARY KEY    |
| `status`          | `Status`                | `GradingStatusEnum` | `grading_status_enum` |
| `grading_rules`   | `GradingRules`          | `List<GradingRule>` | `JSONB`               |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)     | `UUID`                |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)     | `UUID`                |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`          | `TIMESTAMPTZ`         |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)     | `UUID`                |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`         | `TIMESTAMPTZ`         |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)     | `UUID`                |

---

## 15. image_tags

**Script 15:** `image_tags_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `ImageTags`  

### Enums

| PostgreSQL Enum Type    | Values                          | C# Enum         | C# Values                                    |
|:------------------------|:--------------------------------|:----------------|:---------------------------------------------|
| `image_tag_status_enum` | `Unknown`, `Active`, `Disabled` | `TagStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table 15.1: `image_tags`

**PostgreSQL Table:** `image_tags`  
**RavenDB Source:** `ImageTags` (C# `ImageTag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property             | C# Type                      | PostgreSQL Type         |
|:------------------|:------------------------|:-----------------------------|:------------------------|
| `id`              | `Id` *(Entity)*         | `string` (UUID)              | `UUID` PRIMARY KEY      |
| `name`            | `Name`                  | `string`                     | `VARCHAR(255)`          |
| `predefined`      | `Predefined`            | `bool`                       | `BOOLEAN`               |
| `csn`             | `CSN`                   | `string`                     | `VARCHAR(50)`           |
| `meta`            | `Meta`                  | `Dictionary<string, string>` | `JSONB`                 |
| `status`          | `Status`                | `TagStatusEnum`              | `image_tag_status_enum` |
| `owner_id`        | `OwnerId` *(Entity)*    | `string` (UUID)              | `UUID`                  |
| `parent_id`       | `ParentId` *(Entity)*   | `string` (UUID)              | `UUID`                  |
| `created_on`      | `CreatedOn` *(Entity)*  | `DateTime`                   | `TIMESTAMPTZ`           |
| `created_by`      | `CreatedBy` *(Entity)*  | `string` (UUID)              | `UUID`                  |
| `modified_on`     | `ModifiedOn` *(Entity)* | `DateTime?`                  | `TIMESTAMPTZ`           |
| `modified_by`     | `ModifiedBy` *(Entity)* | `string` (UUID)              | `UUID`                  |

---

## 16. institute_calendars

**Script 16:** `institute_calendars_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `InstituteCalendars`  

### Enums

| PostgreSQL Enum Type           | Values                                      | C# Enum                     | C# Values                                                       |
|:-------------------------------|:--------------------------------------------|:----------------------------|:----------------------------------------------------------------|
| `calendar_event_category_enum` | `Event`, `Holiday`, `WeeklyHoliday`, `Exam` | `CalendarEventCategoryEnum` | `Event` = 10, `Holiday` = 20, `WeeklyHoliday` = 30, `Exam` = 40 |

---

### Table 16.1: `institute_calendars`

**PostgreSQL Table:** `institute_calendars`  
**RavenDB Source:** `InstituteCalendars` (C# `InstituteCalendar : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column          | C# Property             | C# Type                     | PostgreSQL Type                |
|:---------------------------|:------------------------|:----------------------------|:-------------------------------|
| `id`                       | `Id` *(Entity)*         | `string` (UUID)             | `UUID` PRIMARY KEY             |
| `inst_id`                  | `InstId`                | `string` (UUID)             | `UUID`                         |
| `event_name`               | `EventName`             | `string`                    | `VARCHAR(255)`                 |
| `event_category`           | `EventCategory`         | `CalendarEventCategoryEnum` | `calendar_event_category_enum` |
| `event_category_as_string` | `EventCategoryAsString` | `string`                    | `VARCHAR(100)`                 |
| `priority`                 | `Priority`              | `int`                       | `INTEGER`                      |
| `audience`                 | `Audience`              | `List<string>`              | `TEXT[]`                       |
| `conducted_by`             | `ConductedBy`           | `List<string>`              | `TEXT[]`                       |
| `event_dates`              | `EventDates`            | `List<Event>`               | `JSONB`                        |
| `owner_id`                 | `OwnerId` *(Entity)*    | `string` (UUID)             | `UUID`                         |
| `parent_id`                | `ParentId` *(Entity)*   | `string` (UUID)             | `UUID`                         |
| `created_on`               | `CreatedOn` *(Entity)*  | `DateTime`                  | `TIMESTAMPTZ`                  |
| `created_by`               | `CreatedBy` *(Entity)*  | `string` (UUID)             | `UUID`                         |
| `modified_on`              | `ModifiedOn` *(Entity)* | `DateTime?`                 | `TIMESTAMPTZ`                  |
| `modified_by`              | `ModifiedBy` *(Entity)* | `string` (UUID)             | `UUID`                         |

---

## 17. inventory

**Script 17:** `inventory_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `InventoryItemViews`, `InventoryJournalViews`  

### Enums

| PostgreSQL Enum Type      | Values               | C# Enum                   | C# Values                     |
|:--------------------------|:---------------------|:--------------------------|:------------------------------|
| `inventory_status_enum`   | `Active`, `Disabled` | `InventoryItemStatusEnum` | `Active` = 1, `Disabled` = 99 |
| `inventory_type_enum`     | `Item`, `Group`      | `InventoryTypeEnum`       | `Item` = 1, `Group` = 2       |
| `journal_entry_type_enum` | `Dr`, `Cr`           | `JournalEntryTypeEnum`    | `Dr` = 10, `Cr` = 20          |

---

### Table 17.1: `inventory_item_views`

**PostgreSQL Table:** `inventory_item_views`  
**RavenDB Source:** `InventoryItemViews` (C# `InventoryItemView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property     | C# Type                      | PostgreSQL Type         |
|:------------------|:----------------|:-----------------------------|:------------------------|
| `id`              | `Id`            | `string` (UUID)              | `UUID` PRIMARY KEY      |
| `name`            | `Name`          | `string`                     | `VARCHAR(255)`          |
| `group_id`        | `GroupId`       | `string` (UUID)              | `UUID`                  |
| `inventory_type`  | `InventoryType` | `InventoryTypeEnum`          | `inventory_type_enum`   |
| `uom`             | `UOM`           | `string`                     | `VARCHAR(50)`           |
| `owner_id`        | `OwnerId`       | `string` (UUID)              | `UUID`                  |
| `tags`            | `Tags`          | `List<string>`               | `TEXT[]`                |
| `attributes`      | `Attributes`    | `Dictionary<string, object>` | `JSONB`                 |
| `status`          | `Status`        | `InventoryItemStatusEnum`    | `inventory_status_enum` |

---

### Table 17.2: `inventory_journal_views`

**PostgreSQL Table:** `inventory_journal_views`  
**RavenDB Source:** `InventoryJournalViews` (C# `InventoryJournalView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column       | C# Property           | C# Type                      | PostgreSQL Type           |
|:------------------------|:----------------------|:-----------------------------|:--------------------------|
| `id`                    | `Id`                  | `string` (UUID)              | `UUID` PRIMARY KEY        |
| `owner_id`              | `OwnerId`             | `string` (UUID)              | `UUID`                    |
| `inventory_item_id`     | `InventoryItemId`     | `string` (UUID)              | `UUID`                    |
| `name`                  | `Name`                | `string`                     | `VARCHAR(255)`            |
| `date`                  | `Date`                | `DateTime`                   | `TIMESTAMPTZ`             |
| `uom`                   | `UOM`                 | `string`                     | `VARCHAR(50)`             |
| `quantity`              | `Quantity`            | `decimal`                    | `NUMERIC(18, 4)`          |
| `rate`                  | `Rate`                | `decimal`                    | `NUMERIC(18, 2)`          |
| `particulars`           | `Particulars`         | `string`                     | `TEXT`                    |
| `reference`             | `Reference`           | `string`                     | `VARCHAR(255)`            |
| `inventory_journal_id`  | `InventoryJournalId`  | `string` (UUID)              | `UUID`                    |
| `accounting_journal_id` | `AccountingJournalId` | `string` (UUID)              | `UUID`                    |
| `party_id`              | `PartyId`             | `string` (UUID)              | `UUID`                    |
| `party_name`            | `PartyName`           | `string`                     | `VARCHAR(255)`            |
| `journal_entry_type`    | `JournalEntryType`    | `JournalEntryTypeEnum`       | `journal_entry_type_enum` |
| `status`                | `Status`              | `InventoryJournalStatusEnum` | `inventory_status_enum`   |

---

## 18. ledger_account_views

**Script 18:** `ledger_account_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `LedgerAccountViews`  

### Enums

| PostgreSQL Enum Type         | Values                                                   | C# Enum                | C# Values                                                                        |
|:-----------------------------|:---------------------------------------------------------|:-----------------------|:---------------------------------------------------------------------------------|
| `ledger_account_status_enum` | `Active`, `Disabled`                                     | `LedgerStatusEnum`     | `Active` = 1, `Disabled` = 99                                                    |
| `nature_of_accounts_enum`    | `Inherit`, `Assets`, `Liabilities`, `Income`, `Expenses` | `NatureOfAccountsEnum` | `Inherit` = 0, `Assets` = 10, `Liabilities` = 20, `Income` = 30, `Expenses` = 40 |
| `ledger_type_enum`           | `Ledger`, `Group`                                        | `LedgerTypeEnum`       | `Ledger` = 1, `Group` = 2                                                        |
| `ledger_owner_type_enum`     | `Org`, `Inst`                                            | `LedgerOwnerTypeEnum`  | `Org` = 1, `Inst` = 2                                                            |

---

### Table 18.1: `ledger_account_views`

**PostgreSQL Table:** `ledger_account_views`  
**RavenDB Source:** `LedgerAccountViews` (C# `LedgerAccountView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column    | C# Property        | C# Type                | PostgreSQL Type              |
|:---------------------|:-------------------|:-----------------------|:-----------------------------|
| `id`                 | `Id`               | `string` (UUID)        | `UUID` PRIMARY KEY           |
| `name`               | `Name`             | `string`               | `VARCHAR(255)`               |
| `group_id`           | `GroupId`          | `string` (UUID)        | `UUID`                       |
| `group_name`         | `GroupName`        | `string`               | `VARCHAR(255)`               |
| `owner_id`           | `OwnerId`          | `string` (UUID)        | `UUID`                       |
| `owner_name`         | `OwnerName`        | `string`               | `VARCHAR(255)`               |
| `owner_type`         | `OwnerType`        | `LedgerOwnerTypeEnum`  | `ledger_owner_type_enum`     |
| `ledger_type`        | `LedgerType`       | `LedgerTypeEnum`       | `ledger_type_enum`           |
| `nature_of_accounts` | `NatureOfAccounts` | `NatureOfAccountsEnum` | `nature_of_accounts_enum`    |
| `status`             | `Status`           | `LedgerStatusEnum`     | `ledger_account_status_enum` |

---

## 19. material_views

**Script 19:** `material_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `MaterialViews`  

### Enums

| PostgreSQL Enum Type   | Values                                                                             | C# Enum              | C# Values                                                                                                      |
|:-----------------------|:-----------------------------------------------------------------------------------|:---------------------|:---------------------------------------------------------------------------------------------------------------|
| `material_status_enum` | `Active`, `Reserved`, `Issued`, `UnderMaintenance`, `OutOfCirculation`, `Disabled` | `MaterialStatusEnum` | `Active` = 1, `Reserved` = 5, `Issued` = 10, `UnderMaintenance` = 20, `OutOfCirculation` = 90, `Disabled` = 99 |

---

### Table 19.1: `material_views`

**PostgreSQL Table:** `material_views`  
**RavenDB Source:** `MaterialViews` (C# `MaterialView : IReadModelLibrary`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column  | C# Property      | C# Type                      | PostgreSQL Type        |
|:-------------------|:-----------------|:-----------------------------|:-----------------------|
| `id`               | `Id`             | `string` (UUID)              | `UUID` PRIMARY KEY     |
| `tracking_id`      | `TrackingId`     | `string`                     | `VARCHAR(100)`         |
| `isbn`             | `ISBN`           | `string`                     | `VARCHAR(100)`         |
| `title`            | `Title`          | `string`                     | `TEXT`                 |
| `author`           | `Author`         | `string`                     | `VARCHAR(255)`         |
| `publisher`        | `Publisher`      | `string`                     | `VARCHAR(255)`         |
| `owner_id`         | `OwnerId`        | `string` (UUID)              | `UUID`                 |
| `ownership`        | `OwnerShip`      | `List<Owner>`                | `JSONB`                |
| `location`         | `Location`       | `string`                     | `VARCHAR(255)`         |
| `attributes`       | `Attributes`     | `Dictionary<string, object>` | `JSONB`                |
| `tags`             | `Tags`           | `List<string>`               | `TEXT[]`               |
| `value`            | `Value`          | `decimal`                    | `NUMERIC(18, 2)`       |
| `status`           | `Status`         | `MaterialStatusEnum`         | `material_status_enum` |
| `last_verified_on` | `LastVerifiedOn` | `long`                       | `BIGINT`               |
| `pages`            | `Pages`          | `int`                        | `INTEGER`              |

---

## 20. member_views

**Script 20:** `member_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `MemberViews`  

### Enums

*No custom enum types defined for this domain.*

---

### Table 20.1: `member_views`

**PostgreSQL Table:** `member_views`  
**RavenDB Source:** `MemberViews` (C# `MemberView : IReadModelLibrary`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property    | C# Type         | PostgreSQL Type    |
|:------------------|:---------------|:----------------|:-------------------|
| `id`              | `Id`           | `string` (UUID) | `UUID` PRIMARY KEY |
| `owner_id`        | `OwnerId`      | `string` (UUID) | `UUID`             |
| `membership_id`   | `MembershipId` | `string`        | `VARCHAR(100)`     |
| `member_type`     | `MemberType`   | `string`        | `VARCHAR(50)`      |
| `issued_books`    | `IssuedBooks`  | `List<string>`  | `TEXT[]`           |

---

## 21. personas

**Script 21:** `personas_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Personas`  

### Enums

| PostgreSQL Enum Type  | Values                                                                                       | C# Enum             | C# Values                                                                                                |
|:----------------------|:---------------------------------------------------------------------------------------------|:--------------------|:---------------------------------------------------------------------------------------------------------|
| `persona_type_enum`   | `0`, `Anon`, `Management`, `Parent`, `Staff`, `Student`, `External`, `Dev`, `35`, `60`, `70` | `PersonaTypeEnum`   | `Anon` = 10, `Management` = 20, `Parent` = 30, `Staff` = 40, `Student` = 50, `External` = 80, `Dev` = 90 |
| `persona_status_enum` | `Unknown`, `Active`, `Disabled`                                                              | `PersonaStatusEnum` | `Unknown` = -1, `Active` = 1, `Disabled` = 99                                                            |

---

### Table 21.1: `persona`

**PostgreSQL Table:** `persona`  
**RavenDB Source:** `Personas` (C# `Persona : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column        | C# Property           | C# Type             | PostgreSQL Type       |
|:-------------------------|:----------------------|:--------------------|:----------------------|
| `id`                     | `Id`                  | `string` (UUID)     | `UUID` PRIMARY KEY    |
| `title`                  | `Title`               | `string`            | `VARCHAR(200)`        |
| `display_text`           | `DisplayText`         | `string`            | `VARCHAR(200)`        |
| `persona_type`           | `PersonaType`         | `PersonaTypeEnum`   | `persona_type_enum`   |
| `persona_type_as_string` | `PersonaTypeAsString` | `string`            | `VARCHAR(64)`         |
| `scope`                  | `Scope`               | `List<string>`      | `TEXT[]`              |
| `named_scope`            | `NamedScope`          | `List<string>`      | `TEXT[]`              |
| `status`                 | `Status`              | `PersonaStatusEnum` | `persona_status_enum` |
| `owner_id`               | `OwnerId`             | `string` (UUID)     | `UUID`                |
| `parent_id`              | `ParentId`            | `string` (UUID)     | `UUID`                |
| `created_on`             | `CreatedOn`           | `DateTime?`         | `TIMESTAMPTZ`         |
| `created_by`             | `CreatedBy`           | `string` (UUID)     | `UUID`                |
| `modified_on`            | `ModifiedOn`          | `DateTime?`         | `TIMESTAMPTZ`         |
| `modified_by`            | `ModifiedBy`          | `string` (UUID)     | `UUID`                |

---

## 22. questions

**Script 22:** `questions_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `QATags`, `Questions`, `RandomQuestionSubmissions`  

### Enums

| PostgreSQL Enum Type        | Values                                                          | C# Enum              | C# Values                                                                                   |
|:----------------------------|:----------------------------------------------------------------|:---------------------|:--------------------------------------------------------------------------------------------|
| `qa_tag_status_enum`        | `Unknown`, `Active`, `Disabled`                                 | `TagStatusEnum`      | `Unknown` = 0, `Active` = 1, `Disabled` = 99                                                |
| `question_status_enum`      | `unknown`, `active`, `disabled`, `published`, `wip`, `archived` | `QuestionStatusEnum` | `unknown` = 0, `active` = 1, `disabled` = 99, `published` = 50, `wip` = 40, `archived` = 80 |
| `question_answer_type_enum` | `Text`, `OneOf`, `ManyOf`                                       | `AnswerEnum`         | `Text` = 1, `OneOf` = 2, `ManyOf` = 3                                                       |
| `question_difficulty_enum`  | `low`, `medium`, `high`                                         | `DifficultyEnum`     | `low` = 10, `medium` = 20, `high` = 30                                                      |

---

### Table 22.1: `qa_tags`

**PostgreSQL Table:** `qa_tags`  
**RavenDB Source:** `QATags` (C# `QATag : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property  | C# Type                      | PostgreSQL Type      |
|:------------------|:-------------|:-----------------------------|:---------------------|
| `id`              | `Id`         | `string` (UUID)              | `UUID` PRIMARY KEY   |
| `name`            | `Name`       | `string`                     | `VARCHAR(255)`       |
| `predefined`      | `Predefined` | `bool`                       | `BOOLEAN`            |
| `csn`             | `CSN`        | `string`                     | `VARCHAR(50)`        |
| `meta`            | `Meta`       | `Dictionary<string, string>` | `JSONB`              |
| `status`          | `Status`     | `TagStatusEnum`              | `qa_tag_status_enum` |
| `owner_id`        | `OwnerId`    | `string` (UUID)              | `UUID`               |
| `parent_id`       | `ParentId`   | `string` (UUID)              | `UUID`               |
| `created_on`      | `CreatedOn`  | `DateTime`                   | `TIMESTAMPTZ`        |
| `created_by`      | `CreatedBy`  | `string` (UUID)              | `UUID`               |
| `modified_on`     | `ModifiedOn` | `DateTime?`                  | `TIMESTAMPTZ`        |
| `modified_by`     | `ModifiedBy` | `string` (UUID)              | `UUID`               |

---

### Table 22.2: `questions`

**PostgreSQL Table:** `questions`  
**RavenDB Source:** `Questions` (C# `Question : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column   | C# Property        | C# Type                      | PostgreSQL Type             |
|:--------------------|:-------------------|:-----------------------------|:----------------------------|
| `id`                | `Id`               | `string` (UUID)              | `UUID` PRIMARY KEY          |
| `question_text`     | `QuestionText`     | `string`                     | `TEXT`                      |
| `plain_text`        | `PlainText`        | `string`                     | `TEXT`                      |
| `html_text`         | `HtmlText`         | `string`                     | `TEXT`                      |
| `tag_list`          | `TagList`          | `List<string>`               | `TEXT[]`                    |
| `options`           | `Options`          | `List<Option>`               | `JSONB`                     |
| `meta`              | `Meta`             | `Dictionary<string, string>` | `JSONB`                     |
| `status`            | `Status`           | `QuestionStatusEnum`         | `question_status_enum`      |
| `answer_type`       | `AnswerType`       | `AnswerEnum`                 | `question_answer_type_enum` |
| `hints`             | `Hints`            | `List<Hint>`                 | `JSONB`                     |
| `instruction`       | `Instruction`      | `string`                     | `TEXT`                      |
| `default_weightage` | `DefaultWeightage` | `decimal`                    | `NUMERIC(10, 2)`            |
| `questions`         | `Questions`        | `List<SubQuestion>`          | `JSONB`                     |
| `difficulty`        | `Difficulty`       | `DifficultyEnum`             | `question_difficulty_enum`  |
| `keywords`          | `Keywords`         | `List<string>`               | `TEXT[]`                    |
| `isn`               | `ISN`              | `string`                     | `VARCHAR(50)`               |
| `answer_text`       | `AnswerText`       | `string`                     | `TEXT`                      |
| `owner_id`          | `OwnerId`          | `string` (UUID)              | `UUID`                      |
| `parent_id`         | `ParentId`         | `string` (UUID)              | `UUID`                      |
| `created_on`        | `CreatedOn`        | `DateTime`                   | `TIMESTAMPTZ`               |
| `created_by`        | `CreatedBy`        | `string` (UUID)              | `UUID`                      |
| `modified_on`       | `ModifiedOn`       | `DateTime?`                  | `TIMESTAMPTZ`               |
| `modified_by`       | `ModifiedBy`       | `string` (UUID)              | `UUID`                      |

---

### Table 22.3: `random_question_submissions`

**PostgreSQL Table:** `random_question_submissions`  
**RavenDB Source:** `RandomQuestionSubmissions` (C# `RandomQuestionSubmission : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column    | C# Property         | C# Type                      | PostgreSQL Type    |
|:---------------------|:--------------------|:-----------------------------|:-------------------|
| `id`                 | `Id`                | `string` (UUID)              | `UUID` PRIMARY KEY |
| `user_id`            | `UserId`            | `string` (UUID)              | `UUID`             |
| `user_email`         | `UserEmail`         | `string`                     | `VARCHAR(255)`     |
| `questions_answered` | `QuestionsAnswered` | `List<RandomQuestionResult>` | `JSONB`            |
| `owner_id`           | `OwnerId`           | `string` (UUID)              | `UUID`             |
| `parent_id`          | `ParentId`          | `string` (UUID)              | `UUID`             |
| `created_on`         | `CreatedOn`         | `DateTime`                   | `TIMESTAMPTZ`      |
| `created_by`         | `CreatedBy`         | `string` (UUID)              | `UUID`             |
| `modified_on`        | `ModifiedOn`        | `DateTime?`                  | `TIMESTAMPTZ`      |
| `modified_by`        | `ModifiedBy`        | `string` (UUID)              | `UUID`             |

---

## 23. receipts

**Script 23:** `receipts_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Receipts`  

### Enums

| PostgreSQL Enum Type        | Values                                      | C# Enum             | C# Values                                                            |
|:----------------------------|:--------------------------------------------|:--------------------|:---------------------------------------------------------------------|
| `receipt_payment_mode_enum` | `Cash`, `Cheque`, `DD`, `Netbanking`, `UPI` | `PaymentModeEnum`   | `Cash` = 10, `Cheque` = 20, `DD` = 30, `Netbanking` = 40, `UPI` = 50 |
| `receipt_status_enum`       | `Active`, `Cancelled`                       | `ReceiptStatusEnum` | `Active` = 1, `Cancelled` = 99                                       |
| `receipt_type_enum`         | `Unknown`, `Regular`, `Donation`            | `ReceiptTypeEnum`   | `Unknown` = 0, `Regular` = 10, `Donation` = 20                       |

---

### Table 23.1: `receipts`

**PostgreSQL Table:** `receipts`  
**RavenDB Source:** `Receipts` (C# `Receipt : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column         | C# Property             | C# Type               | PostgreSQL Type             |
|:--------------------------|:------------------------|:----------------------|:----------------------------|
| `id`                      | `Id`                    | `string` (UUID)       | `UUID` PRIMARY KEY          |
| `number`                  | `Number`                | `string`              | `VARCHAR(50)`               |
| `inst_id`                 | `InstId`                | `string` (UUID)       | `UUID`                      |
| `date`                    | `Date`                  | `DateTime`            | `TIMESTAMPTZ`               |
| `customer`                | `Customer`              | `Customer`            | `JSONB`                     |
| `order_items`             | `OrderItems`            | `List<OrderItem>`     | `JSONB`                     |
| `total_amount`            | `TotalAmount`           | `decimal`             | `NUMERIC(18, 2)`            |
| `received_by`             | `ReceivedBy`            | `string`              | `VARCHAR(150)`              |
| `payment_mode`            | `PaymentMode`           | `PaymentModeEnum`     | `receipt_payment_mode_enum` |
| `financial_instrument`    | `FinancialInstrument`   | `FinancialInstrument` | `JSONB`                     |
| `status`                  | `Status`                | `ReceiptStatusEnum`   | `receipt_status_enum`       |
| `receipt_type`            | `ReceiptType`           | `ReceiptTypeEnum`     | `receipt_type_enum`         |
| `revenue_sharing_enabled` | `RevenueSharingEnabled` | `bool`                | `BOOLEAN`                   |
| `revenue_share`           | `RevenueShare`          | `int`                 | `INTEGER`                   |
| `meta`                    | `Meta`                  | `Meta`                | `JSONB`                     |
| `html`                    | `HTML`                  | `string`              | `TEXT`                      |
| `ref_no`                  | `RefNo`                 | `string`              | `VARCHAR(100)`              |
| `owner_id`                | `OwnerId`               | `string` (UUID)       | `UUID`                      |
| `parent_id`               | `ParentId`              | `string` (UUID)       | `UUID`                      |
| `created_on`              | `CreatedOn`             | `DateTime`            | `TIMESTAMPTZ`               |
| `created_by`              | `CreatedBy`             | `string` (UUID)       | `UUID`                      |
| `modified_on`             | `ModifiedOn`            | `DateTime?`           | `TIMESTAMPTZ`               |
| `modified_by`             | `ModifiedBy`            | `string` (UUID)       | `UUID`                      |

---

## 24. seat_matrices

**Script 24:** `seat_matrices_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `SeatMatrices`  

### Enums

*No custom enum types defined for this domain.*

---

### Table 24.1: `seat_matrices`

**PostgreSQL Table:** `seat_matrices`  
**RavenDB Source:** `SeatMatrices` (C# `SeatMatrix : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property  | C# Type             | PostgreSQL Type    |
|:------------------|:-------------|:--------------------|:-------------------|
| `id`              | `Id`         | `string` (UUID)     | `UUID` PRIMARY KEY |
| `course_id`       | `CourseId`   | `string` (UUID)     | `UUID`             |
| `course`          | `Course`     | `string`            | `VARCHAR(255)`     |
| `total_seats`     | `TotalSeats` | `int`               | `INTEGER`          |
| `break_up`        | `BreakUp`    | `List<SeatBreakUp>` | `JSONB`            |
| `owner_id`        | `OwnerId`    | `string` (UUID)     | `UUID`             |
| `parent_id`       | `ParentId`   | `string` (UUID)     | `UUID`             |
| `created_on`      | `CreatedOn`  | `DateTime`          | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy`  | `string` (UUID)     | `UUID`             |
| `modified_on`     | `ModifiedOn` | `DateTime?`         | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy` | `string` (UUID)     | `UUID`             |

---

## 25. sms

**Script 25:** `sms_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `SMs`, `SmsMessages`  

### Enums

| PostgreSQL Enum Type      | Values                                         | C# Enum                | C# Values                                                        |
|:--------------------------|:-----------------------------------------------|:-----------------------|:-----------------------------------------------------------------|
| `sms_gateway_enum`        | `Unknown`, `Infini`                            | `SMSGatewayEnum`       | `Unknown` = -1, `Infini` = 2                                     |
| `sms_message_status_enum` | `Pending`, `Active`, `Disapproved`, `Disabled` | `SmsMessageStatusEnum` | `Pending` = 0, `Active` = 1, `Disapproved` = 90, `Disabled` = 99 |

---

### Table 25.1: `sms`

**PostgreSQL Table:** `sms`  
**RavenDB Source:** `SMs` (C# `SMS : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property     | C# Type                 | PostgreSQL Type    |
|:------------------|:----------------|:------------------------|:-------------------|
| `id`              | `Id`            | `string` (UUID)         | `UUID` PRIMARY KEY |
| `gateway`         | `Gateway`       | `SMSGatewayEnum`        | `sms_gateway_enum` |
| `gateway_result`  | `GatewayResult` | `string`                | `VARCHAR(500)`     |
| `recipients`      | `Recipients`    | `List<SMSRecipientDto>` | `JSONB`            |
| `message`         | `Message`       | `string`                | `TEXT`             |
| `sms_ref_id`      | `SMSRefId`      | `string`                | `VARCHAR(100)`     |
| `owner_id`        | `OwnerId`       | `string` (UUID)         | `UUID`             |
| `parent_id`       | `ParentId`      | `string` (UUID)         | `UUID`             |
| `created_on`      | `CreatedOn`     | `DateTime`              | `TIMESTAMPTZ`      |
| `created_by`      | `CreatedBy`     | `string` (UUID)         | `UUID`             |
| `modified_on`     | `ModifiedOn`    | `DateTime?`             | `TIMESTAMPTZ`      |
| `modified_by`     | `ModifiedBy`    | `string` (UUID)         | `UUID`             |

---

### Table 25.2: `sms_message`

**PostgreSQL Table:** `sms_message`  
**RavenDB Source:** `SmsMessages` (C# `SmsMessage : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column  | C# Property      | C# Type                | PostgreSQL Type           |
|:-------------------|:-----------------|:-----------------------|:--------------------------|
| `id`               | `Id`             | `string` (UUID)        | `UUID` PRIMARY KEY        |
| `message`          | `Message`        | `string`               | `TEXT`                    |
| `status`           | `Status`         | `SmsMessageStatusEnum` | `sms_message_status_enum` |
| `status_as_string` | `StatusAsString` | `string`               | `VARCHAR(50)`             |
| `length`           | `Length`         | `int`                  | `INTEGER`                 |
| `credits`          | `Credits`        | `int`                  | `INTEGER`                 |
| `reason`           | `Reason`         | `string`               | `TEXT`                    |
| `owner_id`         | `OwnerId`        | `string` (UUID)        | `UUID`                    |
| `parent_id`        | `ParentId`       | `string` (UUID)        | `UUID`                    |
| `created_on`       | `CreatedOn`      | `DateTime`             | `TIMESTAMPTZ`             |
| `created_by`       | `CreatedBy`      | `string` (UUID)        | `UUID`                    |
| `modified_on`      | `ModifiedOn`     | `DateTime?`            | `TIMESTAMPTZ`             |
| `modified_by`      | `ModifiedBy`     | `string` (UUID)        | `UUID`                    |

---

## 26. staffs

**Script 26:** `staffs_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Staffs`  

### Enums

| PostgreSQL Enum Type | Values                          | C# Enum           | C# Values                                     |
|:---------------------|:--------------------------------|:------------------|:----------------------------------------------|
| `staff_gender_enum`  | `Female`, `Male`, `NoInfo`      | `GenderEnum`      | `Female` = 0, `Male` = 1, `NoInfo` = 90       |
| `staff_status_enum`  | `Unknown`, `Active`, `Disabled` | `StaffStatusEnum` | `Unknown` = -1, `Active` = 1, `Disabled` = 99 |

---

### Table 26.1: `staffs`

**PostgreSQL Table:** `staffs`  
**RavenDB Source:** `Staffs` (C# `Staff : Person`, `Person : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column     | C# Property         | C# Type                      | PostgreSQL Type     |
|:----------------------|:--------------------|:-----------------------------|:--------------------|
| `id`                  | `Id`                | `string` (UUID)              | `UUID` PRIMARY KEY  |
| `inst_id`             | `InstId`            | `string` (UUID)              | `UUID`              |
| `doj`                 | `DOJ`               | `DateTime?`                  | `TIMESTAMPTZ`       |
| `designations`        | `Designations`      | `List<Designation>`          | `JSONB`             |
| `status`              | `Status`            | `StaffStatusEnum`            | `staff_status_enum` |
| `employment_history`  | `EmploymentHistory` | `List<Employment>`           | `JSONB`             |
| `course_subject_list` | `CourseSubjectList` | `List<CourseSubject>`        | `JSONB`             |
| `alias`               | `Alias`             | `string`                     | `VARCHAR(200)`      |
| `class_teacher`       | `ClassTeacher`      | `ClassTeacher`               | `JSONB`             |
| `ref_id`              | `RefId`             | `string`                     | `VARCHAR(100)`      |
| `user_id`             | `UserId`            | `string` (UUID)              | `UUID`              |
| `salaries`            | `Salaries`          | `List<Salary>`               | `JSONB`             |
| `payslips`            | `Payslips`          | `List<Payslip>`              | `JSONB`             |
| `first_name`          | `FirstName`         | `string`                     | `VARCHAR(150)`      |
| `middle_name`         | `MiddleName`        | `string`                     | `VARCHAR(150)`      |
| `last_name`           | `LastName`          | `string`                     | `VARCHAR(150)`      |
| `name`                | `Name`              | `string`                     | `VARCHAR(250)`      |
| `title`               | `Title`             | `string`                     | `VARCHAR(50)`       |
| `gender`              | `Gender`            | `GenderEnum?`                | `staff_gender_enum` |
| `dob`                 | `DOB`               | `DateTime?`                  | `TIMESTAMPTZ`       |
| `email`               | `Email`             | `string`                     | `VARCHAR(255)`      |
| `mobile`              | `Mobile`            | `string`                     | `VARCHAR(50)`       |
| `virtual_id`          | `VirtualId`         | `string`                     | `VARCHAR(255)`      |
| `contacts`            | `Contacts`          | `List<Contact>`              | `JSONB`             |
| `addresses`           | `Addresses`         | `List<Address>`              | `JSONB`             |
| `tags`                | `Tags`              | `List<string>`               | `TEXT[]`            |
| `attributes`          | `Attributes`        | `Dictionary<string, object>` | `JSONB`             |
| `owner_id`            | `OwnerId`           | `string` (UUID)              | `UUID`              |
| `parent_id`           | `ParentId`          | `string` (UUID)              | `UUID`              |
| `created_on`          | `CreatedOn`         | `DateTime`                   | `TIMESTAMPTZ`       |
| `created_by`          | `CreatedBy`         | `string` (UUID)              | `UUID`              |
| `modified_on`         | `ModifiedOn`        | `DateTime?`                  | `TIMESTAMPTZ`       |
| `modified_by`         | `ModifiedBy`        | `string` (UUID)              | `UUID`              |

---

## 27. students

**Script 27:** `students_ravendb_to_postgres_migrate.py`  
**RavenDB Collections:** `Orgs`, `Institutes`, `Students`  

### Enums

| PostgreSQL Enum Type       | Values                                                                                    | C# Enum             | C# Values                                                                                                                  |
|:---------------------------|:------------------------------------------------------------------------------------------|:--------------------|:---------------------------------------------------------------------------------------------------------------------------|
| `organization_status_enum` | `Unknown`, `ActivationPending`, `Active`, `Locked`, `Disabled`                            | `ClientStatusEnum`  | `Unknown` = -1, `ActivationPending` = 0, `Active` = 1, `Locked` = 90, `Disabled` = 99                                      |
| `institute_status_enum`    | `Unknown`, `ActivationPending`, `Active`, `Locked`, `Disabled`                            | `ClientStatusEnum`  | `Unknown` = -1, `ActivationPending` = 0, `Active` = 1, `Locked` = 90, `Disabled` = 99                                      |
| `edu_level_enum`           | `Unknown`, `PreNursery`, `Nursery`, `School`, `UnderGraduate`, `Graduate`, `PostGraduate` | `EduLevelEnum`      | `Unknown` = -1, `PreNursery` = 2, `Nursery` = 5, `School` = 10, `UnderGraduate` = 20, `Graduate` = 30, `PostGraduate` = 40 |
| `student_gender_enum`      | `Female`, `Male`, `NoInfo`                                                                | `GenderEnum`        | `Female` = 0, `Male` = 1, `NoInfo` = 90                                                                                    |
| `student_status_enum`      | `Unknown`, `Active`, `Disabled`                                                           | `StudentStatusEnum` | `Unknown` = -1, `Active` = 1, `Disabled` = 99                                                                              |

---

### Table 27.1: `organization`

**PostgreSQL Table:** `organization`  
**RavenDB Source:** `Orgs` (C# `Org : Client`, `Client : Entity, IClient`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column     | C# Property          | C# Type            | PostgreSQL Type            |
|:----------------------|:---------------------|:-------------------|:---------------------------|
| `id`                  | `Id`                 | `string` (UUID)    | `UUID` PRIMARY KEY         |
| `name`                | `Name`               | `string`           | `VARCHAR(200)`             |
| `short_name`          | `ShortName`          | `string`           | `VARCHAR(32)`              |
| `status`              | `Status`             | `ClientStatusEnum` | `organization_status_enum` |
| `created_on`          | `CreatedOn`          | `DateTime`         | `TIMESTAMPTZ`              |
| `modified_on`         | `ModifiedOn`         | `DateTime?`        | `TIMESTAMPTZ`              |
| `website`             | `Website`            | `Contact`          | `TEXT`                     |
| `address`             | `Address`            | `Address`          | `JSONB`                    |
| `sms_sender_id`       | `SMSSenderId`        | `string`           | `VARCHAR(16)`              |
| `email_sender_id`     | `EmailSenderId`      | `string`           | `VARCHAR(320)`             |
| `logo_url`            | `LogoUrl`            | `string`           | `TEXT`                     |
| `is_group`            | `IsGroup`            | `bool`             | `BOOLEAN`                  |
| `is_root`             | `IsRoot`             | `bool`             | `BOOLEAN`                  |
| `modules`             | `Modules`            | `List<string>`     | `TEXT[]`                   |
| `policy_name`         | `PolicyName`         | `string`           | `VARCHAR(100)`             |
| `enable_sms`          | `EnableSMS`          | `bool`             | `BOOLEAN`                  |
| `enable_email`        | `EnableEmail`        | `bool`             | `BOOLEAN`                  |
| `enable_notification` | `EnableNotification` | `bool`             | `BOOLEAN`                  |
| `edu_level`           | `EduLevel`           | `EduLevelEnum`     | `edu_level_enum`           |
| `read_only`           | `ReadOnly`           | `bool`             | `BOOLEAN`                  |
| `owner_id`            | `OwnerId`            | `string` (UUID)    | `UUID`                     |
| `parent_id`           | `ParentId`           | `string` (UUID)    | `UUID`                     |
| `created_by`          | `CreatedBy`          | `string` (UUID)    | `UUID`                     |
| `modified_by`         | `ModifiedBy`         | `string` (UUID)    | `UUID`                     |

---

### Table 27.2: `institute`

**PostgreSQL Table:** `institute`  
**RavenDB Source:** `Institutes` (C# `Institute : Client, IAcademics`, `Client : Entity, IClient`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column         | C# Property             | C# Type            | PostgreSQL Type         |
|:--------------------------|:------------------------|:-------------------|:------------------------|
| `id`                      | `Id`                    | `string` (UUID)    | `UUID` PRIMARY KEY      |
| `name`                    | `Name`                  | `string`           | `VARCHAR(200)`          |
| `short_name`              | `ShortName`             | `string`           | `VARCHAR(6)`            |
| `status`                  | `Status`                | `ClientStatusEnum` | `institute_status_enum` |
| `created_on`              | `CreatedOn`             | `DateTime`         | `TIMESTAMPTZ`           |
| `modified_on`             | `ModifiedOn`            | `DateTime?`        | `TIMESTAMPTZ`           |
| `academic_year_from`      | `AcademicYearFrom`      | `DateTime`         | `TIMESTAMPTZ`           |
| `academic_year_to`        | `AcademicYearTo`        | `DateTime`         | `TIMESTAMPTZ`           |
| `institute_code`          | `InstituteCode`         | `string`           | `VARCHAR(32)`           |
| `registration_number`     | `RegistrationNumber`    | `string`           | `VARCHAR(64)`           |
| `website`                 | `Website`               | `Contact`          | `TEXT`                  |
| `address`                 | `Address`               | `Address`          | `JSONB`                 |
| `sms_sender_id`           | `SMSSenderId`           | `string`           | `VARCHAR(16)`           |
| `email_sender_id`         | `EmailSenderId`         | `string`           | `VARCHAR(320)`          |
| `logo_url`                | `LogoUrl`               | `string`           | `TEXT`                  |
| `is_group`                | `IsGroup`               | `bool`             | `BOOLEAN`               |
| `is_root`                 | `IsRoot`                | `bool`             | `BOOLEAN`               |
| `is_org`                  | `IsOrg`                 | `bool`             | `BOOLEAN`               |
| `modules`                 | `Modules`               | `List<string>`     | `TEXT[]`                |
| `policy_name`             | `PolicyName`            | `string`           | `VARCHAR(100)`          |
| `course_order`            | `CourseOrder`           | `List<string>`     | `TEXT[]`                |
| `enable_sms`              | `EnableSMS`             | `bool`             | `BOOLEAN`               |
| `enable_email`            | `EnableEmail`           | `bool`             | `BOOLEAN`               |
| `enable_notification`     | `EnableNotification`    | `bool`             | `BOOLEAN`               |
| `parental_access_enabled` | `ParentalAccessEnabled` | `bool`             | `BOOLEAN`               |
| `staff_access_enabled`    | `StaffAccessEnabled`    | `bool`             | `BOOLEAN`               |
| `student_access_enabled`  | `StudentAccessEnabled`  | `bool`             | `BOOLEAN`               |
| `edu_level`               | `EduLevel`              | `EduLevelEnum`     | `edu_level_enum`        |
| `read_only`               | `ReadOnly`              | `bool`             | `BOOLEAN`               |
| `owner_id`                | `OwnerId`               | `string` (UUID)    | `UUID`                  |
| `parent_id`               | `ParentId`              | `string` (UUID)    | `UUID`                  |
| `created_by`              | `CreatedBy`             | `string` (UUID)    | `UUID`                  |
| `modified_by`             | `ModifiedBy`            | `string` (UUID)    | `UUID`                  |

---

### Table 27.3: `student`

**PostgreSQL Table:** `student`  
**RavenDB Source:** `Students` (C# `Student : Person`, `Person : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property      | C# Type                      | PostgreSQL Type       |
|:------------------|:-----------------|:-----------------------------|:----------------------|
| `id`              | `Id`             | `string` (UUID)              | `UUID` PRIMARY KEY    |
| `student_id`      | `StudentId`      | `string`                     | `VARCHAR(32)`         |
| `name`            | `Name`           | `string`                     | `VARCHAR(200)`        |
| `first_name`      | `FirstName`      | `string`                     | `VARCHAR(100)`        |
| `middle_name`     | `MiddleName`     | `string`                     | `VARCHAR(100)`        |
| `last_name`       | `LastName`       | `string`                     | `VARCHAR(100)`        |
| `title`           | `Title`          | `string`                     | `VARCHAR(16)`         |
| `gender`          | `Gender`         | `GenderEnum?`                | `student_gender_enum` |
| `dob`             | `DOB`            | `DateTime?`                  | `TIMESTAMPTZ`         |
| `email`           | `Email`          | `string`                     | `VARCHAR(320)`        |
| `mobile`          | `Mobile`         | `string`                     | `VARCHAR(20)`         |
| `email_csv`       | `EmailCSV`       | `string`                     | `TEXT`                |
| `mobile_csv`      | `MobileCSV`      | `string`                     | `TEXT`                |
| `virtual_id`      | `VirtualId`      | `string`                     | `VARCHAR(320)`        |
| `category`        | `Category`       | `string`                     | `VARCHAR(32)`         |
| `attendance`      | `Attendance`     | `string`                     | `JSONB`               |
| `status`          | `Status`         | `StudentStatusEnum`          | `student_status_enum` |
| `user_id`         | `UserId`         | `string` (UUID)              | `UUID`                |
| `inst_id`         | `InstId`         | `string` (UUID)              | `UUID`                |
| `father_name`     | `Father.Name`    | `string`                     | `VARCHAR(200)`        |
| `mother_name`     | `Mother.Name`    | `string`                     | `VARCHAR(200)`        |
| `father`          | `Father`         | `Person`                     | `JSONB`               |
| `mother`          | `Mother`         | `Person`                     | `JSONB`               |
| `guardian`        | `Guardian`       | `Person`                     | `JSONB`               |
| `aadhar_number`   | `AadharNumber`   | `string`                     | `CHAR(12)`            |
| `udid`            | `UDID`           | `string`                     | `VARCHAR(32)`         |
| `domicile`        | `Domicile`       | `Domicile`                   | `JSONB`               |
| `fees_receivable` | `FeesReceivable` | `List<FeesReceivable>`       | `JSONB`               |
| `iep`             | `IEP`            | `IndividualEducationPlan`    | `JSONB`               |
| `documents`       | `Documents`      | `Documents`                  | `JSONB`               |
| `photo_url`       | `PhotoUrl`       | `string`                     | `TEXT`                |
| `contacts`        | `Contacts`       | `List<Contact>`              | `JSONB`               |
| `addresses`       | `Addresses`      | `List<Address>`              | `JSONB`               |
| `tags`            | `Tags`           | `List<string>`               | `TEXT[]`              |
| `attributes`      | `Attributes`     | `Dictionary<string, object>` | `JSONB`               |
| `occupations`     | `Occupations`    | `List<Occupation>`           | `JSONB`               |
| `pan`             | `PAN`            | `string`                     | `CHAR(10)`            |
| `owner_id`        | `OwnerId`        | `string` (UUID)              | `UUID`                |
| `parent_id`       | `ParentId`       | `string` (UUID)              | `UUID`                |
| `enrollments`     | `Enrollments`    | `List<Enrollment>`           | `JSONB`               |
| `created_on`      | `CreatedOn`      | `DateTime`                   | `TIMESTAMPTZ`         |
| `created_by`      | `CreatedBy`      | `string` (UUID)              | `UUID`                |
| `modified_on`     | `ModifiedOn`     | `DateTime?`                  | `TIMESTAMPTZ`         |
| `modified_by`     | `ModifiedBy`     | `string` (UUID)              | `UUID`                |

---

## 28. topics

**Script 28:** `topics_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Topics`  

### Enums

| PostgreSQL Enum Type  | Values                          | C# Enum           | C# Values                                    |
|:----------------------|:--------------------------------|:------------------|:---------------------------------------------|
| `topic_role_enum`     | `Admin`, `Member`               | `RoleEnum`        | `Admin` = 10, `Member` = 20                  |
| `topic_category_enum` | `PrivateToInstitue`, `Public`   | `CategoryEnum`    | `PrivateToInstitue` = 30, `Public` = 40      |
| `topic_access_enum`   | `Open`, `Restricted`            | `AccessEnum`      | `Open` = 50, `Restricted` = 60               |
| `topic_status_enum`   | `Unknown`, `Active`, `Disabled` | `TopicStatusEnum` | `Unknown` = 0, `Active` = 1, `Disabled` = 99 |

---

### Table 28.1: `topics`

**PostgreSQL Table:** `topics`  
**RavenDB Source:** `Topics` (C# `Topic : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column         | C# Property             | C# Type                      | PostgreSQL Type       |
|:--------------------------|:------------------------|:-----------------------------|:----------------------|
| `id`                      | `Id`                    | `string` (UUID)              | `UUID` PRIMARY KEY    |
| `main_topic_id`           | `MainTopicId`           | `string` (UUID)              | `UUID`                |
| `name`                    | `Name`                  | `string`                     | `VARCHAR(255)`        |
| `friendly_name`           | `FriendlyName`          | `string`                     | `VARCHAR(255)`        |
| `description`             | `Description`           | `string`                     | `TEXT`                |
| `role`                    | `Role`                  | `RoleEnum`                   | `topic_role_enum`     |
| `category`                | `Category`              | `CategoryEnum`               | `topic_category_enum` |
| `access`                  | `Access`                | `AccessEnum`                 | `topic_access_enum`   |
| `subscriptions`           | `Subscriptions`         | `dynamic`                    | `JSONB`               |
| `status`                  | `Status`                | `TopicStatusEnum`            | `topic_status_enum`   |
| `meta`                    | `Meta`                  | `Dictionary<string, string>` | `JSONB`               |
| `tags`                    | `Tags`                  | `List<string>`               | `TEXT[]`              |
| `can_unsubscribe`         | `CanUnsubscribe`        | `bool`                       | `BOOLEAN`             |
| `can_publish`             | `CanPublish`            | `bool`                       | `BOOLEAN`             |
| `is_subscription_allowed` | `IsSubscriptionAllowed` | `bool`                       | `BOOLEAN`             |
| `handle`                  | `Handle`                | `string`                     | `VARCHAR(255)`        |
| `owner_id`                | `OwnerId`               | `string` (UUID)              | `UUID`                |
| `parent_id`               | `ParentId`              | `string` (UUID)              | `UUID`                |
| `created_on`              | `CreatedOn`             | `DateTime`                   | `TIMESTAMPTZ`         |
| `created_by`              | `CreatedBy`             | `string` (UUID)              | `UUID`                |
| `modified_on`             | `ModifiedOn`            | `DateTime?`                  | `TIMESTAMPTZ`         |
| `modified_by`             | `ModifiedBy`            | `string` (UUID)              | `UUID`                |

---

## 29. users

**Script 29:** `users_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `Users`  

### Enums

| PostgreSQL Enum Type | Values                                        | C# Enum          | C# Values                                                       |
|:---------------------|:----------------------------------------------|:-----------------|:----------------------------------------------------------------|
| `user_status_enum`   | `Unknown`, `Registered`, `Active`, `Disabled` | `UserStatusEnum` | `Unknown` = -1, `Registered` = 0, `Active` = 1, `Disabled` = 99 |
| `user_gender_enum`   | `Female`, `Male`, `NoInfo`                    | `GenderEnum`     | `Female` = 0, `Male` = 1, `NoInfo` = 90                         |

---

### Table 29.1: `users`

**PostgreSQL Table:** `users`  
**RavenDB Source:** `Users` (C# `User : Person`, `Person : Entity`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column       | C# Property           | C# Type                      | PostgreSQL Type    |
|:------------------------|:----------------------|:-----------------------------|:-------------------|
| `id`                    | `Id`                  | `string` (UUID)              | `UUID` PRIMARY KEY |
| `password`              | `Password`            | `string`                     | `TEXT`             |
| `salt`                  | `Salt`                | `string`                     | `VARCHAR(100)`     |
| `password_reset_on`     | `PasswordResetOn`     | `DateTime?`                  | `TIMESTAMPTZ`      |
| `otp`                   | `OTP`                 | `string`                     | `VARCHAR(50)`      |
| `otp_validity`          | `OTPValidity`         | `DateTime`                   | `TIMESTAMPTZ`      |
| `handle`                | `Handle`              | `string`                     | `VARCHAR(100)`     |
| `force_change_password` | `ForceChangePassword` | `bool`                       | `BOOLEAN`          |
| `password_changed_on`   | `PasswordChangedOn`   | `DateTime?`                  | `TIMESTAMPTZ`      |
| `confirmed_on`          | `ConfirmedOn`         | `DateTime`                   | `TIMESTAMPTZ`      |
| `profile`               | `Profile`             | `Profile`                    | `JSONB`            |
| `preferences`           | `Preferences`         | `Preferences`                | `JSONB`            |
| `status`                | `Status`              | `UserStatusEnum`             | `user_status_enum` |
| `is_virtual`            | `IsVirtual`           | `bool`                       | `BOOLEAN`          |
| `push_notifications`    | `PushNotifications`   | `List<PushNotification>`     | `JSONB`            |
| `personas`              | `Personas`            | `List<string>`               | `TEXT[]`           |
| `current_persona`       | `CurrentPersona`      | `string` (UUID)              | `UUID`             |
| `recovery_email`        | `RecoveryEmail`       | `string`                     | `VARCHAR(255)`     |
| `recovery_mobile`       | `RecoveryMobile`      | `string`                     | `VARCHAR(50)`      |
| `first_name`            | `FirstName`           | `string`                     | `VARCHAR(150)`     |
| `middle_name`           | `MiddleName`          | `string`                     | `VARCHAR(150)`     |
| `last_name`             | `LastName`            | `string`                     | `VARCHAR(150)`     |
| `name`                  | `Name`                | `string`                     | `VARCHAR(250)`     |
| `title`                 | `Title`               | `string`                     | `VARCHAR(50)`      |
| `gender`                | `Gender`              | `GenderEnum?`                | `user_gender_enum` |
| `dob`                   | `DOB`                 | `DateTime?`                  | `TIMESTAMPTZ`      |
| `email`                 | `Email`               | `string`                     | `VARCHAR(255)`     |
| `mobile`                | `Mobile`              | `string`                     | `VARCHAR(50)`      |
| `notification`          | `Notification`        | `bool`                       | `BOOLEAN`          |
| `virtual_id`            | `VirtualId`           | `string`                     | `VARCHAR(255)`     |
| `contacts`              | `Contacts`            | `List<Contact>`              | `JSONB`            |
| `addresses`             | `Addresses`           | `List<Address>`              | `JSONB`            |
| `tags`                  | `Tags`                | `List<string>`               | `TEXT[]`           |
| `attributes`            | `Attributes`          | `Dictionary<string, object>` | `JSONB`            |
| `owner_id`              | `OwnerId`             | `string` (UUID)              | `UUID`             |
| `parent_id`             | `ParentId`            | `string` (UUID)              | `UUID`             |
| `created_on`            | `CreatedOn`           | `DateTime`                   | `TIMESTAMPTZ`      |
| `created_by`            | `CreatedBy`           | `string` (UUID)              | `UUID`             |
| `modified_on`           | `ModifiedOn`          | `DateTime?`                  | `TIMESTAMPTZ`      |
| `modified_by`           | `ModifiedBy`          | `string` (UUID)              | `UUID`             |

---

## 30. voucher_views

**Script 30:** `voucher_views_ravendb_to_postgres_migrate.py`  
**RavenDB Collection:** `VoucherViews`  

### Enums

| PostgreSQL Enum Type  | Values               | C# Enum             | C# Values                     |
|:----------------------|:---------------------|:--------------------|:------------------------------|
| `voucher_type_enum`   | `Expense`            | `VoucherTypeEnum`   | `Expense` = 1                 |
| `voucher_status_enum` | `Active`, `Disabled` | `VoucherStatusEnum` | `Active` = 1, `Disabled` = 99 |

---

### Table 30.1: `voucher_views`

**PostgreSQL Table:** `voucher_views`  
**RavenDB Source:** `VoucherViews` (C# `VoucherView : IReadModelAccounting`)  
**Primary Key:** `id` (`UUID`)  

| PostgreSQL Column | C# Property   | C# Type             | PostgreSQL Type       |
|:------------------|:--------------|:--------------------|:----------------------|
| `id`              | `Id`          | `string` (UUID)     | `UUID` PRIMARY KEY    |
| `owner_id`        | `OwnerId`     | `string` (UUID)     | `UUID`                |
| `description`     | `Description` | `string`            | `TEXT`                |
| `ref_no`          | `RefNo`       | `string`            | `VARCHAR(100)`        |
| `voucher_no`      | `VoucherNo`   | `string`            | `VARCHAR(100)`        |
| `type`            | `Type`        | `VoucherTypeEnum`   | `voucher_type_enum`   |
| `date`            | `Date`        | `DateTime`          | `TIMESTAMPTZ`         |
| `by`              | `By`          | `List<LedgerItem>`  | `JSONB`               |
| `to`              | `To`          | `List<LedgerItem>`  | `JSONB`               |
| `by_total`        | `ByTotal`     | `decimal`           | `NUMERIC(18, 2)`      |
| `to_total`        | `ToTotal`     | `decimal`           | `NUMERIC(18, 2)`      |
| `section`         | `Section`     | `Section`           | `JSONB`               |
| `tags`            | `Tags`        | `List<string>`      | `TEXT[]`              |
| `status`          | `Status`      | `VoucherStatusEnum` | `voucher_status_enum` |
| `created_on`      | `CreatedOn`   | `DateTime`          | `TIMESTAMPTZ`         |

---
