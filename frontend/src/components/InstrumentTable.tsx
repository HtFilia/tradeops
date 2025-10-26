import { FC } from "react";
import { InstrumentSnapshot } from "../lib/api";

interface InstrumentTableProps {
  instruments: InstrumentSnapshot[];
}

const formatNumber = (value: number | undefined, digits = 4) => {
  if (value === undefined || Number.isNaN(value)) {
    return "–";
  }
  return value.toFixed(digits);
};

const formatTime = (iso: string | undefined) => {
  if (!iso) {
    return "–";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

export const InstrumentTable: FC<InstrumentTableProps> = ({ instruments }) => {
  if (instruments.length === 0) {
    return (
      <div className="table-wrapper">
        <table>
          <tbody>
            <tr>
              <td className="empty-state">No snapshots available yet. Waiting for ticks…</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-wrapper">
      <table aria-label="Market data snapshot">
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Mid</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {instruments.map(({ instrumentId, lastTick }) => (
            <tr key={instrumentId}>
              <td>{instrumentId}</td>
              <td>{formatNumber(lastTick?.mid, 4)}</td>
              <td>{formatNumber(lastTick?.bid, 4)}</td>
              <td>{formatNumber(lastTick?.ask, 4)}</td>
              <td>{formatTime(lastTick?.timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
