import { FC } from "react";

interface StatusBadgeProps {
  status: "ok" | "error" | "idle";
  label: string;
}

export const StatusBadge: FC<StatusBadgeProps> = ({ status, label }) => {
  const className =
    status === "ok"
      ? "status-pill status-pill--ok"
      : status === "error"
      ? "status-pill status-pill--error"
      : "status-pill";

  return <span className={className}>{label}</span>;
};
