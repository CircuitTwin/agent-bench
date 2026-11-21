# Runs inside the pinned QEMU image: one ELF on olimex-stm32-h405 (STM32F405), USART2 captured in a file.
# Stops when the firmware prints CT-BENCH-DONE or after the wall limit. Deterministic instruction-count time.
ulimit -f 40000
elf="/fw/$1"
limit="$2"
qemu-system-arm -M olimex-stm32-h405 -kernel "$elf" -display none -monitor none \
    -serial null -serial file:/tmp/serial.txt -icount shift=2,sleep=off \
    -d guest_errors,unimp,int -D /tmp/q.log </dev/null >/tmp/stdout.txt 2>&1 &
pid=$!
i=0
while [ "$i" -lt "$limit" ]; do
    if grep -q CT-BENCH-DONE /tmp/serial.txt 2>/dev/null; then break; fi
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 0.1
    i=$((i + 1))
done
if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid"
    echo "QEMU-STATUS=killed-at-limit"
else
    wait "$pid"
    echo "QEMU-STATUS=exited-$?"
fi
echo "---SERIAL---"
cat /tmp/serial.txt 2>/dev/null
echo "---STDOUT---"
head -c 2000 /tmp/stdout.txt
echo "---FAULTS---"
grep -E "Fault|fault|Abort|Undefined|exception 3" /tmp/q.log 2>/dev/null | head -c 3000
echo "---UNIMP---"
grep "unimplemented device" /tmp/q.log 2>/dev/null | sed 's/ (size.*//' | sort | uniq -c
echo "---GUEST---"
grep -v "unimplemented device" /tmp/q.log 2>/dev/null | grep -iE "guest error|Bad|illegal|invalid" | head -c 1500
