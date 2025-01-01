export class BaseAction<T> {
  static SET_DATA = "SET_DATA";
  static SET_LOADING = "SET_LOADING";
  static SET_ERROR = "SET_ERROR";
  static SET_NOTIFICATION = "SET_NOTIFICATION";

  type: string;
  payload?: T;

  constructor(type: string, payload?: T) {
    this.type = type;
    this.payload = payload;
  }

  static createAction<T>(type: string, payload?: T): BaseAction<T> {
    return new BaseAction<T>(type, payload);
  }
}
