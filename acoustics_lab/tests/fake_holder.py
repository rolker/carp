"""A stand-in for WirePlumber in the reservation tests, run as a program:

    fake_holder.py CARD PRIORITY POLICY

on the bus named by $DBUS_SESSION_BUS_ADDRESS (a private test bus). It
implements the holder's side of org.freedesktop.ReserveDevice1 on its own,
without acoustics_lab. POLICY is "agree" (release to anyone), "refuse" or
"priority" (release only to a higher priority, as the spec says). Prints
"ready" once it owns the name, "released" after letting go, and one line
"asked PRIORITY" per RequestRelease.
"""
import os
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

SERVICE = "org.freedesktop.ReserveDevice1"


class Holder(dbus.service.Object):
    def __init__(self, bus, card, priority, policy):
        self.bus, self.card, self.priority, self.policy = bus, card, priority, policy
        self.name = f"{SERVICE}.Audio{card}"
        super().__init__(bus, f"/org/freedesktop/ReserveDevice1/Audio{card}")

    @dbus.service.method(SERVICE, in_signature="i", out_signature="b")
    def RequestRelease(self, priority):
        print(f"asked {int(priority)}", flush=True)
        agree = (self.policy == "agree"
                 or (self.policy == "priority" and priority > self.priority))
        if agree:
            GLib.idle_add(self.let_go)
        return agree

    def let_go(self):
        self.bus.release_name(self.name)
        print("released", flush=True)
        return False

    props = property(lambda self: {
        "Priority": dbus.Int32(self.priority),
        "ApplicationName": dbus.String("FakeHolder"),
        "ApplicationDeviceName": dbus.String(f"fake_card_{self.card}")})

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss",
                         out_signature="v")
    def Get(self, interface, name):
        return self.props[name]

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s",
                         out_signature="a{sv}")
    def GetAll(self, interface):
        return self.props


def main():
    card, priority, policy = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    DBusGMainLoop(set_as_default=True)
    bus = dbus.bus.BusConnection(os.environ["DBUS_SESSION_BUS_ADDRESS"])
    holder = Holder(bus, card, priority, policy)
    reply = bus.request_name(holder.name, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
    assert reply == dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER
    print("ready", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
