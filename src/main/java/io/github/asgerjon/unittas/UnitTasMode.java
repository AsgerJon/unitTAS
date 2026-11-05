package io.github.asgerjon.unittas;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Whether a unitTAS run was asked for or is going on (README.md), and what the client heard during the current test. */
public final class UnitTasMode {

	/** A unitTAS run's window title, so a window manager can tell it from an ordinary game window: nothing else in it. */
	public static final String WINDOW_TITLE = "unitTAS";

	/** Set when a run starts: the game then leaves the mouse pointer alone and ignores the real mouse and keyboard. */
	public static volatile boolean running;

	/** The sounds the client played during the current test, by name (mixins.client.MixinSoundHandler fills it). */
	public static final List<String> SOUNDS_HEARD = Collections.synchronizedList(new ArrayList<>());

	/**
	 * The sounds the client was asked to play during the current test but doesn't have (no sound event by that name):
	 * these play nothing, silently. A sound exists only if a sounds.json names it.
	 */
	public static final List<String> SOUNDS_UNKNOWN = Collections.synchronizedList(new ArrayList<>());

	/** For each unknown sound, its name and where it was played from (the first calls outside the sound system). */
	public static final List<String> SOUNDS_UNKNOWN_FROM = Collections.synchronizedList(new ArrayList<>());

	/** Told of every sound the client is asked to play during a run (the probe's sound events). */
	public interface SoundListener {
		void played(String id, boolean known, String from, float volume, float pitch, double x, double y, double z);
	}

	public static volatile SoundListener soundListener;

	private UnitTasMode() {
	}

	/** The request ./unittas.sh leaves in the game's folder. */
	public static File request(File gameDir) {
		return new File(gameDir, "unittas/request.properties");
	}

	public static boolean requested(File gameDir) {
		return request(gameDir).isFile();
	}

	/** Forgets every sound heard so far: each test starts with none. */
	public static void clearSounds() {
		SOUNDS_HEARD.clear();
		SOUNDS_UNKNOWN.clear();
		SOUNDS_UNKNOWN_FROM.clear();
	}
}
