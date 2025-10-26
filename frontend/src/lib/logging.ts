type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

interface LogContext {
  [key: string]: unknown;
}

export interface StructuredLogEntry {
  timestamp: string;
  level: LogLevel;
  component: string;
  event: string;
  message: string;
  request_id?: string;
  correlation_id?: string;
  span_id?: string;
  context?: LogContext;
  exception?: string;
}

const COMPONENT_NAME = "ui.trading-board";

function isoTimestamp(): string {
  return new Date().toISOString();
}

function buildPayload(
  level: LogLevel,
  event: string,
  message: string,
  context?: LogContext
): StructuredLogEntry {
  const payload: StructuredLogEntry = {
    timestamp: isoTimestamp(),
    level,
    component: COMPONENT_NAME,
    event,
    message
  };

  if (context && Object.keys(context).length > 0) {
    payload.context = context;
  }

  return payload;
}

function emit(level: LogLevel, event: string, message: string, context?: LogContext): void {
  const payload = buildPayload(level, event, message, context);
  const serialized = JSON.stringify(payload);
  if (level === "ERROR") {
    // eslint-disable-next-line no-console
    console.error(serialized);
  } else if (level === "WARN") {
    // eslint-disable-next-line no-console
    console.warn(serialized);
  } else if (level === "DEBUG") {
    // eslint-disable-next-line no-console
    console.debug(serialized);
  } else {
    // eslint-disable-next-line no-console
    console.log(serialized);
  }
}

export const logger = {
  info(event: string, message: string, context?: LogContext): void {
    emit("INFO", event, message, context);
  },
  error(event: string, message: string, context?: LogContext): void {
    emit("ERROR", event, message, context);
  },
  warn(event: string, message: string, context?: LogContext): void {
    emit("WARN", event, message, context);
  }
};
