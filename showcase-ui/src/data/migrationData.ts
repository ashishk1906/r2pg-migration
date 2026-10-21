import type { CollectionSummary, MigrationParityStats } from '../types/migration';

export const migrationStats: MigrationParityStats = {
  timestampUtc: '2026-10-01T07:55:42.830214+00:00',
  collectionsAuditedCount: 42,
  totalDocumentsInRaven: 2210,
  totalRowsInPostgres: 2210,
  totalMatchedIds: 2210,
  overallStatus: 'PASS',
};

export const collectionSummaries: CollectionSummary[] = [
  {
    id: 'students',
    name: 'Students',
    ravenCollection: 'Students',
    postgresTable: 'student',
    documentCount: 538,
    rowCount: 538,
    matchedCount: 538,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'student_id (UUID)',
    ddl: `-- PostgreSQL Schema for 'student'
CREATE TABLE IF NOT EXISTS student (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL UNIQUE,
    org_id UUID NOT NULL,
    institute_id UUID NOT NULL,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150),
    name VARCHAR(300) NOT NULL,
    email VARCHAR(255),
    enrollment_number VARCHAR(100),
    active BOOLEAN DEFAULT true,
    admission_date DATE,
    enrollments JSONB NOT NULL DEFAULT '[]'::jsonb,
    guardian_details JSONB,
    created_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    modified_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_student_student_id ON student (student_id);
CREATE INDEX IF NOT EXISTS idx_student_name ON student (name);
CREATE INDEX IF NOT EXISTS idx_student_enrollments_gin ON student USING GIN (enrollments);`,
    triggers: `-- Auto-Timestamp Trigger
CREATE OR REPLACE FUNCTION update_modified_on_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_on = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_student_modified_on ON student;
CREATE TRIGGER trg_student_modified_on
BEFORE UPDATE ON student
FOR EACH ROW EXECUTE FUNCTION update_modified_on_column();`,
    indexes: [
      'idx_student_student_id (B-Tree on student_id)',
      'idx_student_name (B-Tree on name)',
      'idx_student_enrollments_gin (GIN Index on enrollments JSONB array)'
    ],
    sampleDocuments: [
      {
        id: 'Students/1042-A',
        metadata: {
          id: 'Students/1042-A',
          clrType: 'CampusTrack.Domain.Student.StudentAggregate, CampusTrack.Core',
          lastModified: '2026-09-28T08:14:22.108Z',
          changeVector: 'A:4812-7XkWqjD5K0'
        },
        rqlQuery: 'from Students where Id = "Students/1042-A"',
        data: {
          Id: 'Students/1042-A',
          StudentId: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          OrgId: 'f0928374-1188-4c33-8991-011244781210',
          InstituteId: '88231209-5431-4a11-8219-550183726190',
          FirstName: 'Aarav',
          LastName: 'Sharma',
          FullName: 'Aarav Sharma',
          Email: 'aarav.sharma@example.edu',
          EnrollmentNumber: 'ENR-2026-042',
          Active: true,
          AdmissionDate: '2026-06-15T00:00:00.000Z',
          Enrollments: [
            {
              CourseId: 'c1010099-1122-4433-8899-776655443322',
              CourseCode: 'CS-401',
              CourseName: 'Distributed Systems & Cloud Computing',
              AcademicYear: '2026-2027',
              Semester: 7,
              Status: 'Enrolled',
              Credits: 4
            },
            {
              CourseId: 'c1010099-1122-4433-8899-776655443323',
              CourseCode: 'CS-405',
              CourseName: 'Database Architecture & Internals',
              AcademicYear: '2026-2027',
              Semester: 7,
              Status: 'Enrolled',
              Credits: 3
            }
          ],
          GuardianDetails: {
            FatherName: 'Rajesh Sharma',
            MotherName: 'Priya Sharma',
            ContactPhone: '+91-9876543210'
          },
          Audit: {
            CreatedAt: '2026-06-15T10:30:00.000Z',
            CreatedBy: 'Admin-System'
          }
        }
      },
      {
        id: 'Students/1043-B',
        metadata: {
          id: 'Students/1043-B',
          clrType: 'CampusTrack.Domain.Student.StudentAggregate, CampusTrack.Core',
          lastModified: '2026-09-28T09:20:11.450Z',
          changeVector: 'A:4813-9KkWmjE7K2'
        },
        rqlQuery: 'from Students where Id = "Students/1043-B"',
        data: {
          Id: 'Students/1043-B',
          StudentId: '8f3d0294-5322-4a00-c2e8-32b5f11203fb',
          OrgId: 'f0928374-1188-4c33-8991-011244781210',
          InstituteId: '88231209-5431-4a11-8219-550183726190',
          FirstName: 'Diya',
          LastName: 'Patel',
          FullName: 'Diya Patel',
          Email: 'diya.patel@example.edu',
          EnrollmentNumber: 'ENR-2026-043',
          Active: true,
          AdmissionDate: '2026-06-18T00:00:00.000Z',
          Enrollments: [
            {
              CourseId: 'c1010099-1122-4433-8899-776655443322',
              CourseCode: 'CS-401',
              CourseName: 'Distributed Systems & Cloud Computing',
              AcademicYear: '2026-2027',
              Semester: 7,
              Status: 'Enrolled',
              Credits: 4
            }
          ],
          GuardianDetails: {
            FatherName: 'Sanjay Patel',
            MotherName: 'Meena Patel',
            ContactPhone: '+91-9812345678'
          }
        }
      }
    ],
    sampleRows: [
      {
        id: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
        sqlQuery: `SELECT student_id, name, email, enrollment_number, active, enrollments, guardian_details, modified_on FROM student WHERE student_id = '7e2c9183-4211-4f99-b1d7-21a4f00192ea';`,
        data: {
          id: '550e8400-e29b-41d4-a716-446655440001',
          student_id: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          org_id: 'f0928374-1188-4c33-8991-011244781210',
          institute_id: '88231209-5431-4a11-8219-550183726190',
          first_name: 'Aarav',
          last_name: 'Sharma',
          name: 'Aarav Sharma',
          email: 'aarav.sharma@example.edu',
          enrollment_number: 'ENR-2026-042',
          active: true,
          admission_date: '2026-06-15',
          enrollments: [
            {
              course_id: 'c1010099-1122-4433-8899-776655443322',
              course_code: 'CS-401',
              course_name: 'Distributed Systems & Cloud Computing',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 4
            },
            {
              course_id: 'c1010099-1122-4433-8899-776655443323',
              course_code: 'CS-405',
              course_name: 'Database Architecture & Internals',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 3
            }
          ],
          guardian_details: {
            father_name: 'Rajesh Sharma',
            mother_name: 'Priya Sharma',
            contact_phone: '+91-9876543210'
          },
          created_on: '2026-06-15 10:30:00+00',
          modified_on: '2026-09-28 08:14:22+00'
        },
        jsonbColumns: {
          enrollments: [
            {
              course_id: 'c1010099-1122-4433-8899-776655443322',
              course_code: 'CS-401',
              course_name: 'Distributed Systems & Cloud Computing',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 4
            },
            {
              course_id: 'c1010099-1122-4433-8899-776655443323',
              course_code: 'CS-405',
              course_name: 'Database Architecture & Internals',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 3
            }
          ],
          guardian_details: {
            father_name: 'Rajesh Sharma',
            mother_name: 'Priya Sharma',
            contact_phone: '+91-9876543210'
          }
        }
      },
      {
        id: '8f3d0294-5322-4a00-c2e8-32b5f11203fb',
        sqlQuery: `SELECT student_id, name, email, enrollment_number, active, enrollments, modified_on FROM student WHERE student_id = '8f3d0294-5322-4a00-c2e8-32b5f11203fb';`,
        data: {
          id: '550e8400-e29b-41d4-a716-446655440002',
          student_id: '8f3d0294-5322-4a00-c2e8-32b5f11203fb',
          org_id: 'f0928374-1188-4c33-8991-011244781210',
          institute_id: '88231209-5431-4a11-8219-550183726190',
          first_name: 'Diya',
          last_name: 'Patel',
          name: 'Diya Patel',
          email: 'diya.patel@example.edu',
          enrollment_number: 'ENR-2026-043',
          active: true,
          admission_date: '2026-06-18',
          enrollments: [
            {
              course_id: 'c1010099-1122-4433-8899-776655443322',
              course_code: 'CS-401',
              course_name: 'Distributed Systems & Cloud Computing',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 4
            }
          ],
          guardian_details: {
            father_name: 'Sanjay Patel',
            mother_name: 'Meena Patel',
            contact_phone: '+91-9812345678'
          },
          created_on: '2026-06-18 11:00:00+00',
          modified_on: '2026-09-28 09:20:11+00'
        },
        jsonbColumns: {
          enrollments: [
            {
              course_id: 'c1010099-1122-4433-8899-776655443322',
              course_code: 'CS-401',
              course_name: 'Distributed Systems & Cloud Computing',
              academic_year: '2026-2027',
              semester: 7,
              status: 'Enrolled',
              credits: 4
            }
          ],
          guardian_details: {
            father_name: 'Sanjay Patel',
            mother_name: 'Meena Patel',
            contact_phone: '+91-9812345678'
          }
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'StudentId',
        postgresColumn: 'student_id',
        sourceType: 'System.Guid (string)',
        targetType: 'UUID',
        transformRule: 'uuid_parse',
        sourceValue: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
        targetValue: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
        isMatched: true,
        notes: 'Regex validated UUID-4'
      },
      {
        ravenField: 'FirstName',
        postgresColumn: 'first_name',
        sourceType: 'String',
        targetType: 'VARCHAR(150)',
        transformRule: 'case_conversion',
        sourceValue: 'Aarav',
        targetValue: 'Aarav',
        isMatched: true
      },
      {
        ravenField: 'FullName',
        postgresColumn: 'name',
        sourceType: 'String',
        targetType: 'VARCHAR(300)',
        transformRule: 'direct',
        sourceValue: 'Aarav Sharma',
        targetValue: 'Aarav Sharma',
        isMatched: true
      },
      {
        ravenField: 'Enrollments[]',
        postgresColumn: 'enrollments (JSONB)',
        sourceType: 'List<EnrollmentDto>',
        targetType: 'JSONB with GIN index',
        transformRule: 'jsonb_array',
        sourceValue: '2 enrollments',
        targetValue: '2 array elements',
        isMatched: true,
        notes: 'Accelerated by GIN (idx_student_enrollments_gin)'
      },
      {
        ravenField: '@metadata.Last-Modified',
        postgresColumn: 'modified_on',
        sourceType: 'ISO-8601 String',
        targetType: 'TIMESTAMPTZ',
        transformRule: 'datetime_utc',
        sourceValue: '2026-09-28T08:14:22.108Z',
        targetValue: '2026-09-28 08:14:22+00',
        isMatched: true,
        notes: 'Maintained automatically via trigger on updates'
      }
    ]
  },
  {
    id: 'fees',
    name: 'Fees',
    ravenCollection: 'Fees',
    postgresTable: 'fee',
    documentCount: 20,
    rowCount: 20,
    matchedCount: 20,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'fee_id (UUID)',
    ddl: `-- PostgreSQL Schema for 'fee'
CREATE TABLE IF NOT EXISTS fee (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fee_id UUID NOT NULL UNIQUE,
    org_id UUID NOT NULL,
    institute_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),
    academic_year VARCHAR(20) NOT NULL,
    amount NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    installments JSONB DEFAULT '[]'::jsonb,
    created_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    modified_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fee_name ON fee (name);
CREATE INDEX IF NOT EXISTS idx_fee_status ON fee (status);`,
    indexes: [
      'idx_fee_name (B-Tree on name)',
      'idx_fee_status (B-Tree on status)'
    ],
    sampleDocuments: [
      {
        id: 'Fees/2026-TUITION-ENG',
        metadata: {
          id: 'Fees/2026-TUITION-ENG',
          clrType: 'CampusTrack.Domain.Fee.FeeStructureAggregate, CampusTrack.Core',
          lastModified: '2026-09-29T06:07:29.000Z',
          changeVector: 'A:2104-3HkLnmQ8P1'
        },
        rqlQuery: 'from Fees where Code = "TUITION-BTECH-26"',
        data: {
          Id: 'Fees/2026-TUITION-ENG',
          FeeId: 'b4018293-1199-4c88-9210-994422110033',
          OrgId: 'f0928374-1188-4c33-8991-011244781210',
          InstituteId: '88231209-5431-4a11-8219-550183726190',
          Name: 'B.Tech Annual Tuition Fee 2026-27',
          Code: 'TUITION-BTECH-26',
          AcademicYear: '2026-2027',
          Amount: 145000.00,
          Status: 'Active',
          Installments: [
            {
              InstallmentNumber: 1,
              Title: 'Term 1 Installment',
              Percentage: 50.0,
              DueDate: '2026-07-31T00:00:00.000Z',
              Amount: 72500.00
            },
            {
              InstallmentNumber: 2,
              Title: 'Term 2 Installment',
              Percentage: 50.0,
              DueDate: '2026-12-15T00:00:00.000Z',
              Amount: 72500.00
            }
          ]
        }
      }
    ],
    sampleRows: [
      {
        id: 'b4018293-1199-4c88-9210-994422110033',
        sqlQuery: `SELECT fee_id, name, code, academic_year, amount, status FROM fee WHERE fee_id = 'b4018293-1199-4c88-9210-994422110033';`,
        data: {
          id: 'aa112233-4455-6677-8899-aabbccddeeff',
          fee_id: 'b4018293-1199-4c88-9210-994422110033',
          name: 'B.Tech Annual Tuition Fee 2026-27',
          code: 'TUITION-BTECH-26',
          academic_year: '2026-2027',
          amount: '145000.00',
          status: 'Active',
          installments: [
            {
              installment_number: 1,
              title: 'Term 1 Installment',
              percentage: 50.0,
              due_date: '2026-07-31',
              amount: 72500.00
            },
            {
              installment_number: 2,
              title: 'Term 2 Installment',
              percentage: 50.0,
              due_date: '2026-12-15',
              amount: 72500.00
            }
          ],
          created_on: '2026-05-10 09:00:00+00',
          modified_on: '2026-09-29 06:07:29+00'
        },
        jsonbColumns: {
          installments: [
            {
              installment_number: 1,
              title: 'Term 1 Installment',
              percentage: 50.0,
              due_date: '2026-07-31',
              amount: 72500.00
            },
            {
              installment_number: 2,
              title: 'Term 2 Installment',
              percentage: 50.0,
              due_date: '2026-12-15',
              amount: 72500.00
            }
          ]
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'FeeId',
        postgresColumn: 'fee_id',
        sourceType: 'Guid',
        targetType: 'UUID',
        transformRule: 'uuid_parse',
        sourceValue: 'b4018293-1199-4c88-9210-994422110033',
        targetValue: 'b4018293-1199-4c88-9210-994422110033',
        isMatched: true
      },
      {
        ravenField: 'Amount',
        postgresColumn: 'amount',
        sourceType: 'Decimal',
        targetType: 'NUMERIC(14,2)',
        transformRule: 'direct',
        sourceValue: 145000.00,
        targetValue: '145000.00',
        isMatched: true
      },
      {
        ravenField: 'Installments',
        postgresColumn: 'installments (JSONB)',
        sourceType: 'List<InstallmentConfig>',
        targetType: 'JSONB array',
        transformRule: 'jsonb_array',
        sourceValue: '2 elements',
        targetValue: '2 JSON objects',
        isMatched: true
      }
    ]
  },
  {
    id: 'fee_transactions',
    name: 'Fee Transactions',
    ravenCollection: 'FeeTxes',
    postgresTable: 'fee_transaction',
    documentCount: 134,
    rowCount: 134,
    matchedCount: 134,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'fee_transaction_id (UUID)',
    ddl: `-- PostgreSQL Schema for 'fee_transaction'
CREATE TABLE IF NOT EXISTS fee_transaction (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    parent_id UUID,
    tx_no VARCHAR(100) NOT NULL UNIQUE,
    tx_date TIMESTAMPTZ NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    ref_no VARCHAR(100),
    paid_by VARCHAR(150),
    fines_paid NUMERIC(14,2) DEFAULT 0.00,
    discounts NUMERIC(14,2) DEFAULT 0.00,
    fee_adjustment NUMERIC(14,2) DEFAULT 0.00,
    is_fine_paid BOOLEAN DEFAULT false,
    is_discount_given BOOLEAN DEFAULT false,
    is_opening_balance_adjusted BOOLEAN DEFAULT false,
    installments_paid JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    modified_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fee_transaction_student_id ON fee_transaction (student_id);
CREATE INDEX IF NOT EXISTS idx_fee_transaction_tx_date ON fee_transaction (tx_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_fee_transaction_tx_no ON fee_transaction (tx_no);
CREATE INDEX IF NOT EXISTS idx_fee_transaction_status ON fee_transaction (status);
CREATE INDEX IF NOT EXISTS idx_fee_transaction_installments_gin ON fee_transaction USING GIN (installments_paid);`,
    triggers: `CREATE TRIGGER trg_fee_transaction_modified_on
BEFORE UPDATE ON fee_transaction
FOR EACH ROW EXECUTE FUNCTION update_modified_on_column();`,
    indexes: [
      'idx_fee_transaction_student_id (B-Tree FK)',
      'idx_fee_transaction_tx_date (B-Tree temporal sorting)',
      'idx_fee_transaction_installments_gin (GIN on JSONB array)'
    ],
    sampleDocuments: [
      {
        id: 'FeeTxes/TX-2026-9041',
        metadata: {
          id: 'FeeTxes/TX-2026-9041',
          clrType: 'CampusTrack.Domain.Fee.FeeTransactionAggregate, CampusTrack.Core',
          lastModified: '2026-09-28T12:25:52.000Z',
          changeVector: 'A:7102-4NkLqmE9R2'
        },
        rqlQuery: 'from FeeTxes where TxNo = "TX-2026-9041"',
        data: {
          Id: 'FeeTxes/TX-2026-9041',
          OwnerId: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          StudentId: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          TxNo: 'TX-2026-9041',
          TxDate: '2026-07-28T14:32:00.000Z',
          Amount: 72500.00,
          Status: 'Active',
          RefNo: 'UPI/2607281432/9021',
          PaidBy: 'Rajesh Sharma',
          FinesPaid: 0.00,
          Discounts: 0.00,
          FeeAdjustment: 0.00,
          IsFinePaid: false,
          IsDiscountGiven: false,
          InstallmentsPaid: [
            {
              FeeId: 'b4018293-1199-4c88-9210-994422110033',
              InstallmentNumber: 1,
              AmountPaid: 72500.00,
              ReceiptNumber: 'RCP-2026-8812'
            }
          ]
        }
      }
    ],
    sampleRows: [
      {
        id: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
        sqlQuery: `SELECT id, tx_no, student_id, amount, status, tx_date, installments_paid FROM fee_transaction WHERE tx_no = 'TX-2026-9041';`,
        data: {
          id: '99018273-3344-5566-7788-99aabbccdde0',
          student_id: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          owner_id: '7e2c9183-4211-4f99-b1d7-21a4f00192ea',
          tx_no: 'TX-2026-9041',
          tx_date: '2026-07-28 14:32:00+00',
          amount: '72500.00',
          status: 'Active',
          ref_no: 'UPI/2607281432/9021',
          paid_by: 'Rajesh Sharma',
          fines_paid: '0.00',
          discounts: '0.00',
          fee_adjustment: '0.00',
          is_fine_paid: false,
          is_discount_given: false,
          installments_paid: [
            {
              fee_id: 'b4018293-1199-4c88-9210-994422110033',
              installment_number: 1,
              amount_paid: 72500.00,
              receipt_number: 'RCP-2026-8812'
            }
          ],
          created_on: '2026-07-28 14:32:00+00',
          modified_on: '2026-09-28 12:25:52+00'
        },
        jsonbColumns: {
          installments_paid: [
            {
              fee_id: 'b4018293-1199-4c88-9210-994422110033',
              installment_number: 1,
              amount_paid: 72500.00,
              receipt_number: 'RCP-2026-8812'
            }
          ]
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'TxNo',
        postgresColumn: 'tx_no',
        sourceType: 'String',
        targetType: 'VARCHAR(100) UNIQUE',
        transformRule: 'case_conversion',
        sourceValue: 'TX-2026-9041',
        targetValue: 'TX-2026-9041',
        isMatched: true
      },
      {
        ravenField: 'TxDate',
        postgresColumn: 'tx_date',
        sourceType: 'DateTime',
        targetType: 'TIMESTAMPTZ',
        transformRule: 'datetime_utc',
        sourceValue: '2026-07-28T14:32:00.000Z',
        targetValue: '2026-07-28 14:32:00+00',
        isMatched: true
      },
      {
        ravenField: 'InstallmentsPaid',
        postgresColumn: 'installments_paid (JSONB)',
        sourceType: 'List<InstallmentPayment>',
        targetType: 'JSONB with GIN Index',
        transformRule: 'jsonb_lateral',
        sourceValue: '1 installment details',
        targetValue: '1 JSON element',
        isMatched: true,
        notes: 'Exploded laterally by student_fee_summary_view'
      }
    ]
  },
  {
    id: 'student_fee_summary_view',
    name: 'Cross-Module Summary View',
    ravenCollection: 'Synthetic / In-Memory Join (C#)',
    postgresTable: 'student_fee_summary_view',
    documentCount: 134,
    rowCount: 134,
    matchedCount: 134,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'fee_transaction_id + fee_id',
    viewDefinition: `CREATE OR REPLACE VIEW student_fee_summary_view AS
WITH raw_paid_installments AS (
    SELECT
        ft.id AS fee_transaction_id,
        ft.owner_id,
        COALESCE(ft.parent_id, ft.owner_id) AS parent_id,
        ft.tx_no,
        ft.tx_date,
        ft.student_id,
        ft.amount AS transaction_amount,
        ft.status AS transaction_status,
        CASE 
            WHEN ft.status = 'Disabled' THEN 99
            WHEN ft.status = 'Active' THEN 1
            ELSE 0
        END AS status_code,
        ft.ref_no,
        ft.paid_by,
        ft.fines_paid,
        ft.discounts,
        ft.fee_adjustment,
        COALESCE(ft.is_fine_paid, false) AS is_fine_paid,
        COALESCE(ft.is_discount_given, false) AS is_discount_given,
        COALESCE(ft.is_opening_balance_adjusted, false) AS is_opening_balance_adjusted,
        NULLIF(COALESCE(
            installment ->> 'FeeId',
            installment ->> 'feeId',
            installment ->> 'Id',
            installment ->> 'fee_id'
        ), '')::UUID AS fee_id,
        COALESCE((installment ->> 'AmountPaid')::NUMERIC, (installment ->> 'amount_paid')::NUMERIC, 0.0) AS installment_amount_paid,
        COALESCE((installment ->> 'InstallmentNumber')::INT, (installment ->> 'installment_number')::INT, 1) AS installment_number,
        COALESCE(installment ->> 'ReceiptNumber', installment ->> 'receipt_number') AS receipt_number
    FROM fee_transaction ft
    CROSS JOIN LATERAL jsonb_array_elements(ft.installments_paid) AS installment
)
SELECT
    rpi.*,
    s.name AS student_name,
    s.enrollment_number,
    s.email AS student_email,
    f.name AS fee_name,
    f.code AS fee_code,
    f.academic_year
FROM raw_paid_installments rpi
LEFT JOIN student s ON s.student_id = rpi.student_id
LEFT JOIN fee f ON f.fee_id = rpi.fee_id;`,
    ddl: `-- PostgreSQL Synchronous Normal View
-- Replaces client-side in-memory joins in .NET with database lateral join
-- Accelerated by GIN indexes on ft.installments_paid and B-Tree on student_id`,
    indexes: ['Accelerated via LATERAL jsonb_array_elements + GIN idx_fee_transaction_installments_gin'],
    sampleDocuments: [
      {
        id: 'RavenDB Multi-Collection Query',
        metadata: {
          id: 'RavenDB: Students + FeeTxes + Fees',
          clrType: 'Multiple Document Reads required (N+1 in-memory join)'
        },
        rqlQuery: `// RavenDB requires 3 roundtrips or multi-map index:
from FeeTxes where Id = "FeeTxes/TX-2026-9041"
// then load Students by OwnerId
// then load Fees by InstallmentsPaid[0].FeeId`,
        data: {
          RavenDB_Pattern: 'Document-per-entity isolation',
          Drawback_in_Raven: 'Required C# in-memory dictionary joins or complex multi-map index',
          Resolution_in_Postgres: 'Native PostgreSQL Normal View with LATERAL jsonb_array_elements join'
        }
      }
    ],
    sampleRows: [
      {
        id: 'view-row-1',
        viewName: 'student_fee_summary_view',
        sqlQuery: `SELECT * FROM student_fee_summary_view WHERE tx_no = 'TX-2026-9041';`,
        data: {
          tx_no: 'TX-2026-9041',
          student_name: 'Aarav Sharma',
          enrollment_number: 'ENR-2026-042',
          student_email: 'aarav.sharma@example.edu',
          fee_name: 'B.Tech Annual Tuition Fee 2026-27',
          fee_code: 'TUITION-BTECH-26',
          academic_year: '2026-2027',
          installment_number: 1,
          installment_amount_paid: 72500.00,
          transaction_amount: 72500.00,
          receipt_number: 'RCP-2026-8812',
          transaction_status: 'Active',
          status_code: 1,
          ref_no: 'UPI/2607281432/9021',
          paid_by: 'Rajesh Sharma'
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'ft.InstallmentsPaid[i].FeeId',
        postgresColumn: 'fee_id (LATERAL extracted)',
        sourceType: 'Nested JSON property',
        targetType: 'UUID column in View',
        transformRule: 'jsonb_lateral',
        sourceValue: 'b4018293-1199-4c88-9210-994422110033',
        targetValue: 'b4018293-1199-4c88-9210-994422110033',
        isMatched: true,
        notes: 'Exploded into 1 row per installment paid'
      },
      {
        ravenField: 'Students.FullName',
        postgresColumn: 'student_name',
        sourceType: 'External Doc field',
        targetType: 'LEFT JOIN s.name',
        transformRule: 'direct',
        sourceValue: 'Aarav Sharma',
        targetValue: 'Aarav Sharma',
        isMatched: true
      },
      {
        ravenField: 'Fees.Name',
        postgresColumn: 'fee_name',
        sourceType: 'External Doc field',
        targetType: 'LEFT JOIN f.name',
        transformRule: 'direct',
        sourceValue: 'B.Tech Annual Tuition Fee 2026-27',
        targetValue: 'B.Tech Annual Tuition Fee 2026-27',
        isMatched: true
      }
    ]
  },
  {
    id: 'applications',
    name: 'Applications',
    ravenCollection: 'Applications',
    postgresTable: 'applications',
    documentCount: 7,
    rowCount: 7,
    matchedCount: 7,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'id (UUID)',
    ddl: `CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID NOT NULL,
    applicant_name VARCHAR(255) NOT NULL,
    applicant_email VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'Submitted',
    form_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    submitted_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    modified_on TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);`,
    indexes: ['idx_applications_template_id (B-Tree)', 'idx_applications_form_data (GIN)'],
    sampleDocuments: [
      {
        id: 'Applications/APP-2026-001',
        metadata: {
          id: 'Applications/APP-2026-001',
          clrType: 'CampusTrack.Domain.Admissions.ApplicationAggregate',
          lastModified: '2026-09-21T16:56:54.000Z'
        },
        rqlQuery: 'from Applications where Id = "Applications/APP-2026-001"',
        data: {
          Id: 'Applications/APP-2026-001',
          TemplateId: '99018273-1122-3344-5566-778899aabbcc',
          ApplicantName: 'Rohan Mehra',
          ApplicantEmail: 'rohan.mehra@example.com',
          Status: 'Submitted',
          FormData: {
            PreviousSchool: 'Delhi Public School',
            GPA: 9.4,
            SelectedStream: 'Computer Science'
          }
        }
      }
    ],
    sampleRows: [
      {
        id: '99018273-1122-3344-5566-778899aabbcc',
        sqlQuery: `SELECT * FROM applications WHERE applicant_name = 'Rohan Mehra';`,
        data: {
          id: '12345678-1234-1234-1234-123456789abc',
          template_id: '99018273-1122-3344-5566-778899aabbcc',
          applicant_name: 'Rohan Mehra',
          applicant_email: 'rohan.mehra@example.com',
          status: 'Submitted',
          form_data: {
            previous_school: 'Delhi Public School',
            gpa: 9.4,
            selected_stream: 'Computer Science'
          },
          submitted_on: '2026-09-21 16:56:54+00'
        },
        jsonbColumns: {
          form_data: {
            previous_school: 'Delhi Public School',
            gpa: 9.4,
            selected_stream: 'Computer Science'
          }
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'ApplicantName',
        postgresColumn: 'applicant_name',
        sourceType: 'String',
        targetType: 'VARCHAR(255)',
        transformRule: 'case_conversion',
        sourceValue: 'Rohan Mehra',
        targetValue: 'Rohan Mehra',
        isMatched: true
      }
    ]
  },
  {
    id: 'courses',
    name: 'Courses',
    ravenCollection: 'Courses',
    postgresTable: 'course',
    documentCount: 353,
    rowCount: 353,
    matchedCount: 353,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'course_id (UUID)',
    ddl: `CREATE TABLE IF NOT EXISTS course (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL UNIQUE,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    credits INT DEFAULT 3,
    department VARCHAR(100),
    syllabus JSONB DEFAULT '{}'::jsonb
);`,
    indexes: ['idx_course_code (B-Tree UNIQUE)', 'idx_course_department (B-Tree)'],
    sampleDocuments: [
      {
        id: 'Courses/CS-401',
        metadata: {
          id: 'Courses/CS-401',
          clrType: 'CampusTrack.Domain.Curriculum.CourseAggregate'
        },
        rqlQuery: 'from Courses where Code = "CS-401"',
        data: {
          Id: 'Courses/CS-401',
          CourseId: 'c1010099-1122-4433-8899-776655443322',
          Code: 'CS-401',
          Name: 'Distributed Systems & Cloud Computing',
          Credits: 4,
          Department: 'Computer Science'
        }
      }
    ],
    sampleRows: [
      {
        id: 'c1010099-1122-4433-8899-776655443322',
        sqlQuery: `SELECT * FROM course WHERE code = 'CS-401';`,
        data: {
          id: 'aa889900-1122-3344-5566-77889900aabb',
          course_id: 'c1010099-1122-4433-8899-776655443322',
          code: 'CS-401',
          name: 'Distributed Systems & Cloud Computing',
          credits: 4,
          department: 'Computer Science',
          terms: [
            {
              term_number: 1,
              syllabus: ['Cloud Principles', 'CAP Theorem', 'Consensus Algorithms (Raft/Paxos)'],
              evaluation_weight: 40
            },
            {
              term_number: 2,
              syllabus: ['Distributed Storage', 'Event Sourcing', 'PostgreSQL JSONB & GIN'],
              evaluation_weight: 60
            }
          ]
        },
        jsonbColumns: {
          terms: [
            {
              term_number: 1,
              syllabus: ['Cloud Principles', 'CAP Theorem', 'Consensus Algorithms (Raft/Paxos)'],
              evaluation_weight: 40
            },
            {
              term_number: 2,
              syllabus: ['Distributed Storage', 'Event Sourcing', 'PostgreSQL JSONB & GIN'],
              evaluation_weight: 60
            }
          ]
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'Code',
        postgresColumn: 'code',
        sourceType: 'String',
        targetType: 'VARCHAR(50)',
        transformRule: 'case_conversion',
        sourceValue: 'CS-401',
        targetValue: 'CS-401',
        isMatched: true
      }
    ]
  },
  {
    id: 'personas',
    name: 'Personas (Identity)',
    ravenCollection: 'Personas',
    postgresTable: 'persona',
    documentCount: 620,
    rowCount: 620,
    matchedCount: 620,
    missingInPg: 0,
    extraInPg: 0,
    fieldMismatches: 0,
    status: 'PASS',
    primaryKey: 'persona_id (UUID)',
    ddl: `CREATE TABLE IF NOT EXISTS persona (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    persona_id UUID NOT NULL UNIQUE,
    user_id UUID NOT NULL,
    role VARCHAR(50) NOT NULL,
    claims JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT true
);`,
    indexes: ['idx_persona_user_id (B-Tree)', 'idx_persona_role (B-Tree)'],
    sampleDocuments: [
      {
        id: 'Personas/USR-9921',
        metadata: {
          id: 'Personas/USR-9921',
          clrType: 'CampusTrack.Domain.Identity.PersonaAggregate'
        },
        rqlQuery: 'from Personas where Id = "Personas/USR-9921"',
        data: {
          Id: 'Personas/USR-9921',
          PersonaId: 'e2018822-4433-2211-9988-776655443322',
          UserId: 'u1010101-2222-3333-4444-555566667777',
          Role: 'Student',
          IsActive: true,
          Claims: ['STUDENT_PORTAL_READ', 'FEE_RECEIPT_DOWNLOAD']
        }
      }
    ],
    sampleRows: [
      {
        id: 'e2018822-4433-2211-9988-776655443322',
        sqlQuery: `SELECT * FROM persona WHERE persona_id = 'e2018822-4433-2211-9988-776655443322';`,
        data: {
          id: 'bb334455-6677-8899-0011-223344556677',
          persona_id: 'e2018822-4433-2211-9988-776655443322',
          user_id: 'u1010101-2222-3333-4444-555566667777',
          role: 'Student',
          claims: ['STUDENT_PORTAL_READ', 'FEE_RECEIPT_DOWNLOAD'],
          is_active: true
        },
        jsonbColumns: {
          claims: ['STUDENT_PORTAL_READ', 'FEE_RECEIPT_DOWNLOAD']
        }
      }
    ],
    fieldMappings: [
      {
        ravenField: 'PersonaId',
        postgresColumn: 'persona_id',
        sourceType: 'Guid',
        targetType: 'UUID',
        transformRule: 'uuid_parse',
        sourceValue: 'e2018822-4433-2211-9988-776655443322',
        targetValue: 'e2018822-4433-2211-9988-776655443322',
        isMatched: true
      }
    ]
  }
];

export const allAuditedDomainsList = [
  { domain: 'Students', collection: 'Students', table: 'student', count: 538, fields: 43 },
  { domain: 'Fees', collection: 'Fees', table: 'fee', count: 20, fields: 18 },
  { domain: 'Fee Transactions', collection: 'FeeTxes', table: 'fee_transaction', count: 134, fields: 24 },
  { domain: 'Applications', collection: 'Applications', table: 'applications', count: 7, fields: 16 },
  { domain: 'Courses', collection: 'Courses', table: 'course', count: 353, fields: 21 },
  { domain: 'Personas', collection: 'Personas', table: 'persona', count: 620, fields: 19 },
  { domain: 'Organizations', collection: 'Orgs', table: 'organization', count: 15, fields: 26 },
  { domain: 'Institutes', collection: 'Institutes', table: 'institute', count: 25, fields: 32 },
  { domain: 'Exams', collection: 'Exams', table: 'exam', count: 88, fields: 17 },
  { domain: 'Staffs', collection: 'Staffs', table: 'staffs', count: 142, fields: 28 },
  { domain: 'Attendance Events', collection: 'AttendanceEvents', table: 'attendance_event', count: 74, fields: 15 },
  { domain: 'Assessments', collection: 'Assessments', table: 'assessments', count: 52, fields: 19 },
  { domain: 'Inventory Items', collection: 'InventoryItemViews', table: 'inventory_item_views', count: 48, fields: 22 },
  { domain: 'Ledger Accounts', collection: 'LedgerAccountViews', table: 'ledger_account_views', count: 36, fields: 20 },
  { domain: 'Receipts', collection: 'Receipts', table: 'receipts', count: 31, fields: 18 },
  { domain: 'Questions (QA)', collection: 'Questions', table: 'questions', count: 96, fields: 25 },
  { domain: 'Topics', collection: 'Topics', table: 'topics', count: 44, fields: 14 },
  { domain: 'Voucher Views', collection: 'VoucherViews', table: 'voucher_views', count: 28, fields: 17 },
  { domain: 'Users', collection: 'Users', table: 'users', count: 85, fields: 21 },
  { domain: 'SMS Messages', collection: 'SmsMessages', table: 'sms_message', count: 19, fields: 12 },
  { domain: 'Emails', collection: 'Emails', table: 'email', count: 22, fields: 14 }
];
