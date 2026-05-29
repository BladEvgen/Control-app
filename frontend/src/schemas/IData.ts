export class BaseState<T> {
  data: T | null;
  error: string;
  loading: boolean;
  showNotification: boolean;

  constructor(data: T | null = null) {
    this.data = data;
    this.error = "";
    this.loading = true;
    this.showNotification = false;
  }
}
export interface ITokenResponse {
  refresh: string;
  access: string;
  access_token_expires: string;
  refresh_token_expires: string;
  user: {
    username: string;
    is_banned: boolean;
    is_staff: boolean;
    is_super: boolean;
  };
}

export interface IUserDetails {
  user: {
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    date_joined: string;
    last_login: string | null;
    phonenumber: string;
    is_banned: boolean;
    last_login_ip: string | null;
  };
}

export class ExtendedState<T> extends BaseState<T> {
  startDate: string;
  endDate: string;
  oneMonthDataFetched: boolean;

  constructor(data: T | null = null) {
    super(data);
    this.startDate = "";
    this.endDate = "";
    this.oneMonthDataFetched = false;
  }
}

export interface IChildDepartment {
  child_id: string | number;
  name: string;
  date_of_creation: string;
  parent: string | number;
  has_child_departments: boolean;
}

export interface IBreadcrumbPathItem {
  id: string;
  name: string;
}

export interface IData {
  name: string;
  date_of_creation: string;
  child_departments: IChildDepartment[];
  total_staff_count: number;
  breadcrumb_path?: IBreadcrumbPathItem[];
}

export interface IStaffData {
  [key: string]: {
    FIO: string;
    date_of_creation: string;
    avatar: string | null;
    positions: string[];
  };
}
export interface IChildDepartmentData {
  child_department: IChildDepartment;
  staff_count: number;
  staff_data: IStaffData;
  breadcrumb_path?: IBreadcrumbPathItem[];
}

export interface StaffData {
  name: string;
  surname: string;
  positions: string[];
  avatar: string;
  department: string;
  department_id: number;
  attendance: Record<string, AttendanceData>;
  lesson_attendance_audit?: Record<string, LessonAttendanceDayAudit>;
  percent_for_period: number;
  bonus_percentage: number;
  contract_type: string | null;
  salary: number | null;
}

export type LessonDayStatus = "ok" | "pending_manual_review" | "rejected_fraud";

export interface LessonAttendanceAuditLesson {
  lesson_attendance_id: number;
  subject_name: string;
  first_in: string | null;
  last_out: string | null;
  photo_spoof_status: string;
  photo_manual_verdict: string;
  rejected_in_merged_attendance_report: boolean;
  treated_as_confirmed_for_display: boolean;
  awaits_manual_review: boolean;
  fraud_attempt: boolean;
}

export interface LessonAttendanceDayAudit {
  has_lessons: boolean;
  lesson_day_status: LessonDayStatus;
  day_confirmed_for_accounting: boolean;
  fraud_attempted: boolean;
  awaiting_manual_review: boolean;
  lessons: LessonAttendanceAuditLesson[];
  summary_ru: string;
}

export interface AreaSequencePoint {
  t: string;
  area: string;
  devSn?: string;
  is_exit?: string;
  exit_candidate?: string;
  exit_resolution?: string;
}

export interface AttendanceData {
  first_in: string | null;
  last_out: string | null;
  percent_day: number;
  total_minutes: number;
  effective_work_seconds?: number | null;
  area_sequence?: AreaSequencePoint[] | null;
  is_weekend: boolean;
  is_remote_work: boolean;
  is_absent_approved: boolean;
  absent_reason: string | null;
  lesson_attendance_day?: LessonAttendanceDayAudit | null;
}

export interface AttendanceStatsPresentItem {
  staff_pin: string;
  name: string;
  minutes_present?: number;
  individual_percentage: number;
}

export interface AttendanceStats {
  department_name: string;
  total_staff_count: number;
  present_staff_count: number;
  absent_staff_count: number;
  present_between_9_to_18?: number;
  present_data: AttendanceStatsPresentItem[];
  absent_data: Array<{ staff_pin: string; name: string }>;
  data_for_date: string;
}

export interface LocationData {
  name: string;
  address: string;
  lat: number;
  lng: number;
  employees: number;
}

export interface PhotoData {
  id?: number;
  hasPhoto?: boolean;
  staffPin: string;
  staffFullName: string;
  department: string;
  photoUrl: string;
  attendanceTime: string;
  tutorInfo: string;
  photoSpoofStatus?: PhotoSpoofStatus;
  photoSpoofScore?: number | null;
  photoSpoofTags?: string[];
  photoSpoofCheckedAt?: string | null;
  photoSpoofModelVersion?: string;
  photoTrustConfirmed?: boolean | null;
  photoManualVerdict?: PhotoManualVerdict;
  photoEffectiveStatus?: PhotoSpoofStatus;
  photoEffectiveTrustConfirmed?: boolean | null;
  photoCanSetManualVerdict?: boolean;
  stateCode?: PhotoStateCode;
  versionTs?: string;
  op?: PhotoWsOp;
}

export type PhotoSpoofStatus =
  | "pending"
  | "clean"
  | "review"
  | "suspicious"
  | "error";

export type PhotoManualVerdict = "none" | "clean" | "suspicious";

export type PhotoStateCode =
  | "SNAPSHOT"
  | "CREATED_NO_PHOTO"
  | "PHOTO_ATTACHED"
  | "UPDATED_META"
  | "DELETED";

export type PhotoWsOp = "snapshot" | "created" | "updated" | "deleted";

export interface PhotoWsMessage {
  type?: "initial_photos" | "photos_updated" | "heartbeat" | "ping" | "pong";
  protocol?: string;
  batchId?: string;
  chunkIndex?: number;
  totalChunks?: number;
  sentAt?: string;
  events?: PhotoData[];
  photos?: PhotoData[];
  newPhoto?: PhotoData;
}
