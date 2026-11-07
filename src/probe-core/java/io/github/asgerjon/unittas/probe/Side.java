package io.github.asgerjon.unittas.probe;

/** A thread of the game that ticks (PROTOCOL.md 4.1): the client's or the integrated server's. */
public enum Side {
	CLIENT("client"),
	SERVER("server");

	/** Its name on the wire. */
	public final String wire;

	Side(String wire) {
		this.wire = wire;
	}

	/** The side the wire names, or null for a name that is neither. */
	public static Side of(String wire) {
		for (Side side : values()) {
			if (side.wire.equals(wire)) {
				return side;
			}
		}
		return null;
	}
}
