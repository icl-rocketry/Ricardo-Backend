import socket
import json
import time
def startUDPForwarder(args, receiveQueue):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    udp_addr = (args['udp_host'], args['udp_port'])
    print(f"✅ UDP Forwarder sending to {udp_addr}")

    while True:
        try:
            data = receiveQueue.get_nowait()
        except:
            time.sleep(0.001)
            continue

        # print("\n🔹 RAW FROM QUEUE:", type(data), data)

        try:
            # Case 1: already a dict
            if isinstance(data, dict):
                print("✅ DICT received:", data)
                payload = data.get("data", data)

            # Case 2: bytes
            elif isinstance(data, (bytes, bytearray)):
                print("✅ BYTES received:", data[:50], "...")
                try:
                    decoded = data.decode()
                    # print("🔹 decoded:", decoded)
                    parsed = json.loads(decoded)
                    # print("🔹 parsed:", parsed)
                    payload = parsed.get("data", parsed)
                except Exception as e:
                    print("❌ JSON decode failed:", e)
                    sock.sendto(data, udp_addr)
                    continue

            # Case 3: string
            elif isinstance(data, str):
                # print("✅ STRING received:", data)
                try:
                    parsed = json.loads(data)
                    # print("🔹 parsed:", parsed)
                    payload = parsed.get("data", parsed)
                except Exception as e:
                    print("❌ JSON decode failed:", e)
                    sock.sendto(data.encode(), udp_addr)
                    continue

            else:
                print("❓ UNKNOWN TYPE:", type(data))
                sock.sendto(str(data).encode(), udp_addr)
                continue

            # print("🔹 PAYLOAD:", payload)

            # ✅ ONLY do dict processing if payload is dict
            if isinstance(payload, dict):
                for key in ['state','flag_info','flag_error','flightphase']:
                    payload.pop(key, None)

                # print("🔹 CLEAN PAYLOAD:", payload)

                values = list(payload.values())
                # print("🔹 VALUES:", values)

                packet = " ".join(map(str, values)).encode()
            else:
                print("🔹 NON-DICT PAYLOAD SENT:", payload)
                packet = str(payload).encode()

            # print("📤 UDP SEND:", packet)
            sock.sendto(packet, udp_addr)

        except Exception as e:
            print("UDP send error:", e)
