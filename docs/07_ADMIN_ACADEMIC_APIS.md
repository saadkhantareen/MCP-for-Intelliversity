# Admin Academic APIs Documentation

## Overview

The Admin Academic APIs provide endpoints for managing core academic entities. These endpoints are tenant-aware and require admin/staff authentication. The APIs implement full CRUD operations for Departments, Programs, Courses, and Curriculum.

**Status**: ✅ **Documented & Ready for Implementation** as of April 29, 2026

---

## Base URL

```
POST/GET/PATCH/DELETE /api/v1/academics/
```

All endpoints are nested under `/api/v1/academics/` with trailing slashes.

---

## Authentication

All academic endpoints require:
- **Authentication**: JWT Bearer Token in `Authorization` header
  ```
  Authorization: Bearer {access_token}
  ```
- **Tenant Context**: Automatically resolved via multi-tenancy middleware
- **Permissions**: Admin or staff role required (permission checks in views)

---

## Endpoints Reference

### 1. Departments

#### List Departments
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/departments/`
- **Authentication**: Required
- **Response**:
  ```json
  {
    "count": 5,
    "results": [
      {
        "id": 1,
        "name": "Computer Science",
        "code": "CS",
        "description": "Department of Computer Science"
      }
    ]
  }
  ```

#### Retrieve Department
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/departments/{id}/`
- **Auth**: Required
- **Response**: Single department object

#### Create Department
- **Method**: `POST`
- **Endpoint**: `/api/v1/academics/departments/`
- **Auth**: Required
- **Request Body**:
  ```json
  {
    "name": "Computer Science",
    "code": "CS",
    "description": "Department of Computer Science"
  }
  ```
- **Response**: Created department object with `id`

#### Update Department
- **Method**: `PATCH`
- **Endpoint**: `/api/v1/academics/departments/{id}/`
- **Auth**: Required
- **Request Body**: Any combination of fields
- **Response**: Updated department object

#### Delete Department
- **Method**: `DELETE`
- **Endpoint**: `/api/v1/academics/departments/{id}/`
- **Auth**: Required
- **Response**: `204 No Content` or `204` status

---

### 2. Programs

#### List Programs
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/programs/`
- **Response**:
  ```json
  {
    "count": 10,
    "results": [
      {
        "id": 1,
        "name": "Bachelor of Science",
        "code": "BS",
        "department": 1,
        "department_name": "Computer Science",
        "degree_level": "undergraduate",
        "duration_years": 4,
        "description": "4-year BSc program"
      }
    ]
  }
  ```

#### Retrieve Program
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/programs/{id}/`
- **Response**: Single program object

#### Create Program
- **Method**: `POST`
- **Endpoint**: `/api/v1/academics/programs/`
- **Request Body**:
  ```json
  {
    "name": "Bachelor of Science",
    "code": "BS",
    "department": 1,
    "degree_level": "undergraduate",
    "duration_years": 4,
    "description": "4-year BSc program"
  }
  ```

#### Update Program
- **Method**: `PATCH`
- **Endpoint**: `/api/v1/academics/programs/{id}/`

#### Delete Program
- **Method**: `DELETE`
- **Endpoint**: `/api/v1/academics/programs/{id}/`

---

### 3. Courses

#### List Courses
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/courses/`
- **Query Parameters**: 
  - `department` (optional): Filter by department ID
- **Response**:
  ```json
  {
    "count": 45,
    "results": [
      {
        "id": 1,
        "code": "CS101",
        "name": "Introduction to Programming",
        "department": 1,
        "department_name": "Computer Science",
        "credit_hours": 3,
        "semester": 1,
        "description": "Foundational programming course"
      }
    ]
  }
  ```

#### Retrieve Course
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/courses/{id}/`
- **Response**: Single course object with prerequisites array

#### Get Course Prerequisites
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/courses/{id}/prerequisites/`
- **Response**:
  ```json
  {
    "course_id": 1,
    "prerequisites": [
      {
        "id": 2,
        "code": "CS100",
        "name": "Basic Math"
      }
    ]
  }
  ```

#### Create Course
- **Method**: `POST`
- **Endpoint**: `/api/v1/academics/courses/`
- **Request Body**:
  ```json
  {
    "code": "CS101",
    "name": "Introduction to Programming",
    "department": 1,
    "credit_hours": 3,
    "semester": 1,
    "description": "Foundational programming course",
    "prerequisite_courses": [2, 3]
  }
  ```

#### Update Course
- **Method**: `PATCH`
- **Endpoint**: `/api/v1/academics/courses/{id}/`

#### Delete Course
- **Method**: `DELETE`
- **Endpoint**: `/api/v1/academics/courses/{id}/`

---

### 4. Curriculum

#### List Curriculum
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/curriculum/`
- **Response**:
  ```json
  {
    "count": 8,
    "results": [
      {
        "id": 1,
        "name": "BSc Computer Science 2024",
        "program": 1,
        "program_name": "Bachelor of Science",
        "version": "1.0",
        "is_active": true,
        "created_at": "2024-01-15T10:30:00Z"
      }
    ]
  }
  ```

#### Retrieve Curriculum
- **Method**: `GET`
- **Endpoint**: `/api/v1/academics/curriculum/{id}/`
- **Response**: Single curriculum object with associated courses

#### Create Curriculum
- **Method**: `POST`
- **Endpoint**: `/api/v1/academics/curriculum/`
- **Request Body**:
  ```json
  {
    "name": "BSc Computer Science 2024",
    "program": 1,
    "version": "1.0",
    "is_active": true,
    "courses": [1, 2, 3, 4, 5]
  }
  ```

#### Update Curriculum
- **Method**: `PATCH`
- **Endpoint**: `/api/v1/academics/curriculum/{id}/`

#### Delete Curriculum
- **Method**: `DELETE`
- **Endpoint**: `/api/v1/academics/curriculum/{id}/`

---

## Error Handling

All endpoints follow standard HTTP error codes:

```
200 OK              - Successful GET/PATCH
201 Created         - Successful POST
204 No Content      - Successful DELETE
400 Bad Request     - Invalid request data
401 Unauthorized    - Missing/invalid token
403 Forbidden       - Insufficient permissions
404 Not Found       - Resource not found
500 Server Error    - Backend failure
```

### Error Response Format
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Field Reference

### Department Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | integer | Auto | Read-only |
| name | string | Yes | Max 255 chars |
| code | string | Yes | Unique per tenant |
| description | string | No | Max 1000 chars |

### Program Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | integer | Auto | Read-only |
| name | string | Yes | Max 255 chars |
| code | string | Yes | Unique per tenant |
| department | integer | Yes | Foreign key to Department |
| degree_level | string | Yes | (undergraduate, postgraduate) |
| duration_years | integer | Yes | Must be > 0 |
| description | string | No | Max 1000 chars |

### Course Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | integer | Auto | Read-only |
| code | string | Yes | Unique per tenant |
| name | string | Yes | Max 255 chars |
| department | integer | Yes | Foreign key |
| credit_hours | integer | Yes | 1-4 typical |
| semester | integer | Yes | 1-8 typical |
| description | string | No | Max 1000 chars |
| prerequisite_courses | array | No | List of course IDs |

### Curriculum Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | integer | Auto | Read-only |
| name | string | Yes | Max 255 chars |
| program | integer | Yes | Foreign key |
| version | string | No | Semantic versioning |
| is_active | boolean | No | Default true |
| courses | array | No | List of course IDs |

---

## Frontend Integration

The frontend admin portal consumes these APIs via service layer:

- `/src/services/department.service.js` - Departments CRUD
- `/src/services/program.service.js` - Programs CRUD
- `/src/services/course.service.js` - Courses CRUD
- `/src/services/curriculum.service.js` - Curriculum CRUD

### Frontend Pages
- `/departments` - Departments management UI
- `/programs` - Programs management UI
- `/courses` - Courses management UI (with department filter)
- `/curriculum` - Curriculum management UI

**See**: `/frontend/docs/context/11-admin-academic-pages.md` for complete frontend documentation.

---

## Multi-Tenancy Considerations

All endpoints are automatically scoped to the current tenant via:

1. **Middleware Resolution**: `TenantMiddleware` extracts tenant from request
2. **Database Router**: `UniversityDatabaseRouter` routes queries to tenant database
3. **Query Filtering**: All models include tenant-specific queries (implicit via router)

### Example Multi-Tenant Flow
```
GET /api/v1/academics/departments/
  → Middleware identifies tenant ("university-a")
  → Router switches to "university_a_db"
  → Query returns only "university-a" departments
  → Router switches back to main DB for response
```

---

## Future Enhancements

1. **Bulk Operations**: POST endpoint for bulk import (CSV/Excel)
2. **Academic Terms**: Terms/Semesters management
3. **Course Scheduling**: Timetable and room allocation
4. **Grades & Assessments**: Grading scales and schema
5. **Prerequisites Graph**: Validation of course prerequisite chains
6. **Analytics**: Curriculum coverage analysis, enrollment trends

---

## Implementation Checklist

- [ ] Create Django models for Department, Program, Course, Curriculum
- [ ] Create serializers for each model with nested FK resolution
- [ ] Create viewsets with academic permissions
- [ ] Register routes in `apps/academics/urls.py`
- [ ] Run migrations: `python manage.py makemigrations academics`
- [ ] Add tests for CRUD endpoints
- [ ] Seed sample data for testing
- [ ] Document in Swagger (drf-spectacular integration)
- [ ] Update main API schema: `http://localhost:8000/api/v1/schema/`
