package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasHooks;
import io.github.asgerjon.unittas.TasPlugin;

/** unitTAS's own plugin, in its tests' source set: counts the world hooks, for WorldFreshBTests. */
@TasPlugin
public class SelfPlugin implements TasHooks {

	static volatile int worldsSetUp;
	static volatile int worldsTornDown;

	@Override
	public void setUpWorld() {
		worldsSetUp++;
	}

	@Override
	public void tearDownWorld() {
		worldsTornDown++;
	}
}
