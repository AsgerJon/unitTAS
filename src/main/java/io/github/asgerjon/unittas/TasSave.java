package io.github.asgerjon.unittas;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * The save a run in save mode has open: its folder, which load it is (1: as found, 2: after this game saved it),
 * where its pristine copy is, and what was logged while it loaded.
 */
public final class TasSave {

	/** The open save, or null outside save mode. */
	static volatile TasSave current;

	public final String folder;
	public final int pass;
	/** The pristine copy of the save (as vanilla left it), or null if the request named none. */
	public final File pristine;
	/** The building list next to it (`<folder>.buildings`). */
	public final File buildings;
	/** Logged while the save loaded, up to the player being in it and settled. */
	public final List<String> loadErrors = new ArrayList<>();
	public final List<String> loadWarnings = new ArrayList<>();
	/** The listener, still listening while the tests run (each takes what it adds). */
	public final TasLogErrors log;
	/** If the listener couldn't start: why. */
	String listenerProblem;
	/** Seconds from asking for the save to the player in it. */
	public double loadSeconds;

	TasSave(String folder, int pass, File oldSaves, TasLogErrors log) {
		this.folder = folder;
		this.pass = pass;
		this.pristine = oldSaves == null ? null : new File(oldSaves, folder);
		this.buildings = oldSaves == null ? null : new File(oldSaves, folder + ".buildings");
		this.log = log;
	}

	public String listenerProblem() {
		return listenerProblem;
	}

	/** The save a run in save mode has open, or null. */
	public static TasSave current() {
		return current;
	}
}
