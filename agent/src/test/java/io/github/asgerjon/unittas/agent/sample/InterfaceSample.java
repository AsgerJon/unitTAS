package io.github.asgerjon.unittas.agent.sample;

/** An interface's default method: the rewriter hooks classes only, and refuses it. */
public interface InterfaceSample {

	default int answer() {
		return 42;
	}
}
