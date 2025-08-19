#!/usr/bin/env python3
import argparse, json, random, signal, string, sys, time
from datetime import datetime, timezone, timedelta
from kafka import KafkaProducer

def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")

def mk_id(prefix="MTR", n=5):
    return f"{prefix}-{''.join(random.choices(string.digits, k=n))}"

def main():
    ap = argparse.ArgumentParser(description="Generate sensor events to Kafka")
    ap.add_argument("--brokers", required=True, help="Comma-separated list, e.g. kafka:9092")
    ap.add_argument("--topic", required=True, default="sensor_events")
    ap.add_argument("--rate", type=float, default=50, help="messages per second")
    ap.add_argument("--duration", type=int, default=0, help="seconds (0 = infinite)")
    ap.add_argument("--n-devices", type=int, default=25)
    ap.add_argument("--sites", nargs="*", default=["fab1","fab2"])
    ap.add_argument("--lines", nargs="*", default=["L01","L02","L03"])
    ap.add_argument("--key-by", choices=["none","device_id"], default="device_id")
    ap.add_argument("--p-hot", type=float, default=0.05, help="probability of HOT anomaly (temp)")
    ap.add_argument("--p-vib", type=float, default=0.05, help="probability of VIB anomaly (vibration)")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    devices = [mk_id("MTR",5) for _ in range(max(1,args.n-devices if hasattr(args,'n-devices') else args.n_devices))] \
              if hasattr(args,'n-devices') else [mk_id("MTR",5) for _ in range(max(1,args.n_devices))]

    # Backward compatibility for argparse attr with dash
    if hasattr(args, 'n-devices'):
        args.n_devices = getattr(args, 'n-devices')

    devices = [mk_id("MTR",5) for _ in range(max(1,args.n_devices))]

    producer = KafkaProducer(
        bootstrap_servers=[b.strip() for b in args.brokers.split(",")],
        acks=1,
        linger_ms=50,
        batch_size=64_000,
        retries=5,
        value_serializer=lambda v: json.dumps(v, separators=(",", ":")).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
    )

    # Graceful shutdown
    stop = {"flag": False}
    def _sig(*_):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    interval = 1.0 / max(1e-6, args.rate)
    start = time.perf_counter()
    sent = 0

    try:
        while not stop["flag"]:
            now = iso_now()
            dev = random.choice(devices)
            site = random.choice(args.sites)
            line = random.choice(args.lines)

            # Base signals
            temp = random.normalvariate(75.0, 4.0)
            vib  = max(0.01, random.normalvariate(0.12, 0.05))

            # Inject anomalies with given probabilities
            if random.random() < args.p_hot: temp = random.uniform(86.0, 100.0)
            if random.random() < args.p_vib: vib  = random.uniform(0.55, 1.2)

            status_flags = []
            if temp > 85.0: status_flags.append("HOT")
            if vib  > 0.5:  status_flags.append("VIB")
            status = "OK" if not status_flags else "_".join(status_flags)

            event = {
                "device_id": dev,
                "ts": now,  # event time in ISO8601 UTC
                "temperature_c": round(temp, 2),
                "vibration_g": round(vib, 3),
                "status": status,
                "site": site,
                "line": line,
            }

            key = dev if args.key_by == "device_id" else None
            producer.send(args.topic, value=event, key=key)
            sent += 1

            # pacing
            target = start + sent * interval
            while True:
                t = time.perf_counter()
                if t >= target: break
                time.sleep(min(0.002, target - t))

            # progress heartbeat
            if sent % max(1, int(args.rate)) == 0:
                sys.stdout.write(f"\rSent {sent} msgs … last status={status}     ")
                sys.stdout.flush()

            # duration stop
            if args.duration and (t - start) >= args.duration:
                break

    finally:
        sys.stdout.write("\nFlushing…\n")
        producer.flush(10)
        producer.close()
        print(f"Done. Sent {sent} messages to {args.topic}.")

if __name__ == "__main__":
    main()
