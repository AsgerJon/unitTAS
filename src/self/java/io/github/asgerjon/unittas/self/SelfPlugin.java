package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasHooks;
import io.github.asgerjon.unittas.TasPlugin;

/**
 * unitTAS's own plugin, in its tests' source set: counts the world hooks of the run, for WorldFreshBTests. From zero at
 * each run's start: one game can hold several (the probe's java.run), and hooks.run calls them outside any run.
 */
@TasPlugin
public class SelfPlugin implements TasHooks {

	static volatile int worldsSetUp;
	static volatile int worldsTornDown;

	@Override
	public void beforeRun() {
		worldsSetUp = 0;
		worldsTornDown = 0;
	}

	@Override
	public void setUpWorld() {
		worldsSetUp++;
	}

	@Override
	public void tearDownWorld() {
		worldsTornDown++;
	}
}
