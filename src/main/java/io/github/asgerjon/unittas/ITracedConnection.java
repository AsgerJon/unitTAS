package io.github.asgerjon.unittas;

/**
 * A connection named in the loading trace (TasTrace; `mixins.client.MixinNetworkManagerTrace` adds it to
 * NetworkManager): which one it is and its channel's state, so a trace tells two connections apart.
 */
public interface ITracedConnection {

	/** "#1a2b3c server, channel none yet | open | CLOSED". */
	String unittas$traceDescription();

	static String describe(Object connection) {
		return connection instanceof ITracedConnection ? ((ITracedConnection) connection).unittas$traceDescription()
			: "#" + Integer.toHexString(System.identityHashCode(connection));
	}
}
